import asyncio
import copy
import importlib.util
import os
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

from generation_session import Session, Pipeline
from test_generation import CONFIG, PNG, until


class CleanupTests(unittest.IsolatedAsyncioTestCase):
    async def test_cleanup_only_after_both_images_and_json_and_ack(self):
        with tempfile.TemporaryDirectory() as tmp:
            config=copy.deepcopy(CONFIG)
            config['generation']['samples']=1
            config['comfyui']['cleanup']={'enabled':True}
            session=Session(config,Path(tmp)); pipeline=Pipeline(session)
            seen=[]
            def clean(url, prompt_id, options):
                root=session.output
                assert (root/'original/photoId_00001.png').is_file()
                assert (root/'transparent/photoId_00001.png').is_file()
                assert (root/'parameters/photoId_00001.json').is_file()
                seen.append(prompt_id)
            with patch.dict(os.environ, {'PHOTO_ID_CLEANUP_TOKEN':'test'}), patch('generation_session.submit_image',return_value='original'), patch('generation_session.submit_background',return_value='background'), patch('generation_session.wait_image',return_value=PNG), patch('remote_cleanup.cleanup',side_effect=clean):
                pipeline.start()
                await until(lambda: len(seen)==2)
                await pipeline.stop()
            self.assertEqual(set(seen),{'original','background'})
            self.assertEqual(session.db.execute('SELECT COUNT(*) FROM cleanup_queue').fetchone()[0],0)
            self.assertIsNone(session.next('done')['remote_id'])
            session.close()

    async def test_cleanup_failure_remains_pending_without_failing_portrait(self):
        with tempfile.TemporaryDirectory() as tmp:
            config=copy.deepcopy(CONFIG);config['generation']['samples']=1
            config['comfyui']['cleanup']={'enabled':True}
            session=Session(config,Path(tmp));pipeline=Pipeline(session)
            with patch.dict(os.environ,{'PHOTO_ID_CLEANUP_TOKEN':'test'}),patch('generation_session.submit_image',return_value='original'),patch('generation_session.submit_background',return_value='background'),patch('generation_session.wait_image',return_value=PNG),patch('remote_cleanup.cleanup',side_effect=RuntimeError('offline')):
                pipeline.start()
                await until(lambda: session.counts().get('done')==1)
                await asyncio.sleep(.02)
                await pipeline.stop()
            self.assertEqual(session.db.execute('SELECT COUNT(*) FROM cleanup_queue').fetchone()[0],2)
            self.assertFalse(pipeline.paused)
            session.close()


class ExtensionPathTests(unittest.TestCase):
    def test_scoped_paths_and_rejection(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=types.SimpleNamespace(get_output_directory=lambda:tmp,get_input_directory=lambda:tmp)
            routes=types.SimpleNamespace(post=lambda route: lambda fn:fn)
            server=types.SimpleNamespace(PromptServer=types.SimpleNamespace(instance=types.SimpleNamespace(routes=routes)))
            aiohttp=types.ModuleType('aiohttp');aiohttp.web=types.SimpleNamespace()
            with patch.dict('sys.modules',{'folder_paths':folder,'server':server,'aiohttp':aiohttp}):
                spec=importlib.util.spec_from_file_location('cleanup_extension',Path(__file__).resolve().parents[1]/'comfyui_extensions/ds_photo_id_cleanup/__init__.py')
                module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            good={'type':'output','subfolder':'photo_id','filename':'photoId_00001_00001_.png'}
            self.assertEqual(module.owned_path(good),Path(tmp)/'photo_id/photoId_00001_00001_.png')
            for changes in ({'subfolder':'../outside'},{'subfolder':'other'},{'filename':'../../secret'},{'filename':'unrelated.png'}):
                with self.assertRaises(ValueError):module.owned_path({**good,**changes})
            upload={'type':'input','filename':'photo_id_'+'a'*32+'.webp','subfolder':''}
            self.assertEqual(module.owned_path(upload).name,upload['filename'])
            with self.assertRaises(ValueError):module.owned_path({**upload,'filename':'user-photo.png'})


class ExtensionRequestTests(unittest.IsolatedAsyncioTestCase):
    async def test_authenticated_cleanup_deletes_only_owned_files_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'photo_id').mkdir()
            target=root/'photo_id/photoId_00001_00001_.png';target.write_bytes(PNG)
            unrelated=root/'unrelated.png';unrelated.write_bytes(PNG)
            entry={'status':{'status_str':'success'},'prompt':[None,None,{}],
                   'outputs':{'461':{'images':[{'type':'output','subfolder':'photo_id','filename':target.name}]}}}
            queue=types.SimpleNamespace(get_history=lambda prompt_id:{prompt_id:entry})
            routes=types.SimpleNamespace(post=lambda route:lambda fn:fn)
            server=types.SimpleNamespace(PromptServer=types.SimpleNamespace(instance=types.SimpleNamespace(routes=routes,prompt_queue=queue)))
            folder=types.SimpleNamespace(get_output_directory=lambda:tmp,get_input_directory=lambda:tmp)
            aiohttp=types.ModuleType('aiohttp');aiohttp.web=types.SimpleNamespace(json_response=lambda body,status=200:{'body':body,'status':status})
            with patch.dict('sys.modules',{'folder_paths':folder,'server':server,'aiohttp':aiohttp}):
                spec=importlib.util.spec_from_file_location('cleanup_request_test',Path(__file__).resolve().parents[1]/'comfyui_extensions/ds_photo_id_cleanup/__init__.py')
                module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            class Request:
                headers={}
                async def json(self):return {'prompt_ids':['job']}
            request=Request()
            with patch.dict(os.environ,{'PHOTO_ID_CLEANUP_TOKEN':'secret'}):
                self.assertEqual((await module.cleanup(request))['status'],401)
                self.assertTrue(target.exists())
                request.headers={'Authorization':'Bearer secret'}
                for _ in range(2):
                    self.assertTrue((await module.cleanup(request))['body']['ok'])
                self.assertFalse(target.exists())
                self.assertTrue(unrelated.exists())
