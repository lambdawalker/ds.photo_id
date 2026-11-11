import asyncio
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from datasets import Dataset
from generation_session import Session, Pipeline
from incremental_upload import LiveUploader, send_shard
from test_generation import CONFIG, PNG, until


def config():
    result=copy.deepcopy(CONFIG)
    result['generation']['samples']=3
    result['huggingface']={'enabled':True,'repo_id':'example/portraits','batch_size':2,
                           'interval_seconds':300,'retry_seconds':60}
    return result


def complete(session, ids):
    for i in ids:
        session.update(i,prompt=f'Exact prompt {i}',state='done')
        job=session.db.execute('SELECT * FROM jobs WHERE id=?',(i,)).fetchone()
        image,prompt=session.paths(job)
        image.write_bytes(PNG);prompt.write_text(job['prompt'])
        session.transparent_path(job).write_bytes(PNG)
        session.originals.add(job['stem'])
        session.write_parameters(i)


class IncrementalUploadTests(unittest.IsolatedAsyncioTestCase):
    async def test_batches_embed_images_flush_tail_and_resume_without_duplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            session=Session(config(),Path(tmp));complete(session,[1,2,3])
            p=Pipeline(session);u=LiveUploader(p);remote={}
            def send(repo,private,path,remote_path):remote[remote_path]=path.read_bytes()
            with patch('incremental_upload.send_shard',side_effect=send):
                u.start();await until(lambda:u.snapshot()['uploaded']==3);await u.stop()
            self.assertEqual(len(remote),2)
            ids=[]
            for index,data in enumerate(remote.values()):
                shard=Path(tmp)/f'remote-{index}.parquet';shard.write_bytes(data)
                dataset=Dataset.from_parquet(str(shard))
                ids.extend(dataset['id'])
                self.assertEqual(dataset[0]['image_transparent'].mode,'RGBA')
                self.assertTrue(json.loads(dataset[0]['parameters'])['sample'])
            self.assertEqual(len(set(ids)),3)
            session.close()
            session=Session(config(),Path(tmp));u=LiveUploader(Pipeline(session))
            with patch('incremental_upload.send_shard') as send:
                u.start();await asyncio.sleep(.03);await u.stop();send.assert_not_called()
            self.assertEqual(u.snapshot()['uploaded'],3);session.close()

    async def test_lost_ack_reuses_same_immutable_shard_after_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            session=Session(config(),Path(tmp));complete(session,[1,2])
            u=LiveUploader(Pipeline(session));attempts=[]
            def lost(repo,private,path,remote_path):
                attempts.append((remote_path,hashlib.sha256(path.read_bytes()).hexdigest()))
                raise TimeoutError('commit succeeded but acknowledgement was lost')
            with patch('incremental_upload.send_shard',side_effect=lost):
                u.start();await until(lambda:u.status=='retrying');await u.stop()
            self.assertEqual(u.snapshot()['uploaded'],0)
            session.close()
            session=Session(config(),Path(tmp));u=LiveUploader(Pipeline(session))
            def success(repo,private,path,remote_path):
                attempts.append((remote_path,hashlib.sha256(path.read_bytes()).hexdigest()))
            with patch('incremental_upload.send_shard',side_effect=success),patch('incremental_upload.make_shard',side_effect=AssertionError('must reuse staged file')):
                u.start();await until(lambda:u.snapshot()['uploaded']==2);await u.stop()
            self.assertEqual(len(set(attempts)),1)
            self.assertEqual(u.snapshot()['pending'],0);session.close()

    async def test_upload_worker_runs_with_generation_and_drains_on_exit(self):
        with tempfile.TemporaryDirectory() as tmp:
            session=Session(config(),Path(tmp));p=Pipeline(session)
            with patch('generation_session.submit_image',return_value='original'),patch('generation_session.submit_background',return_value='background'),patch('generation_session.wait_image',return_value=PNG),patch('incremental_upload.send_shard') as send:
                p.start()
                await until(lambda:p.uploader.snapshot()['uploaded']==3)
                await p.stop()
                self.assertEqual(send.call_count,2)
            self.assertEqual(p.upload_snapshot()['uploaded'],3)
            self.assertEqual(p.upload_snapshot()['status'],'stopped')
            session.close()

    async def test_blocked_upload_does_not_block_prompt_or_image_workers(self):
        import threading
        from incremental_upload import report
        with tempfile.TemporaryDirectory() as tmp:
            settings=config();settings['huggingface']['batch_size']=1
            session=Session(settings,Path(tmp));events=[]
            p=Pipeline(session,lambda stage,message:events.append((stage,message)))
            entered=threading.Event();release=threading.Event()
            llm_calls=0
            def llm(draft,*args):
                nonlocal llm_calls
                llm_calls+=1
                if llm_calls==3 and not entered.wait(5):raise TimeoutError('uploader did not start')
                return draft
            def image(remote,stem,*args):
                if remote=='original' and stem=='photoId_00002' and not entered.wait(5):raise TimeoutError('uploader did not start')
                return PNG
            def blocked(*args):
                report('Uploading test shard')
                entered.set()
                if not release.wait(5):raise TimeoutError('test timed out')
            with patch('generation_session.submit_image',return_value='original'),patch('generation_session.submit_background',return_value='background'),patch('generation_session.wait_image',side_effect=image),patch('generation_session.finalize_prompt',side_effect=llm),patch('incremental_upload.send_shard',side_effect=blocked):
                p.start()
                try:
                    await until(lambda:entered.is_set() and session.counts().get('done')==3)
                    self.assertEqual(p.upload_snapshot()['uploaded'],0)
                    self.assertEqual(p.upload_snapshot()['status'],'uploading')
                    self.assertTrue(any(stage=='upload' and 'test shard' in message for stage,message in events))
                    self.assertFalse(any(stage=='image' and 'Hugging Face' in message for stage,message in events))
                finally:
                    release.set()
                await until(lambda:p.upload_snapshot()['uploaded']==3)
                await p.stop()
            session.close()

    async def test_retry_now_bypasses_retry_countdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            session=Session(config(),Path(tmp));complete(session,[1,2]);u=LiveUploader(Pipeline(session))
            with patch('incremental_upload.send_shard',side_effect=[TimeoutError('offline'),None]):
                u.start()
                await until(lambda:u.status=='retrying')
                self.assertGreater(u.snapshot()['retry_in_seconds'],0)
                self.assertEqual(u.snapshot()['batch_records'],2)
                u.retry()
                await until(lambda:u.snapshot()['uploaded']==2)
                await u.stop()
            session.close()

    async def test_paused_uploads_and_shutdown_flush(self):
        with tempfile.TemporaryDirectory() as tmp:
            session=Session(config(),Path(tmp));complete(session,[1])
            p=Pipeline(session);p.paused=True;u=LiveUploader(p)
            with patch('incremental_upload.send_shard') as send:
                u.start();await asyncio.sleep(.03);send.assert_not_called()
                await u.stop()
                self.assertEqual(send.call_count,1)
            self.assertEqual(u.snapshot()['uploaded'],1);session.close()

    async def test_timer_uploads_small_batch_while_generation_is_incomplete(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings=config();settings['huggingface']['interval_seconds']=.02
            session=Session(settings,Path(tmp));complete(session,[1]);u=LiveUploader(Pipeline(session))
            with patch('incremental_upload.send_shard') as send:
                u.start();await until(lambda:u.snapshot()['uploaded']==1);await u.stop()
                self.assertEqual(send.call_count,1)
            session.close()


class HubCommitTests(unittest.TestCase):
    def test_atomic_shard_and_card_use_revision_lease(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'batch.parquet';path.write_bytes(b'shard')
            with patch('huggingface_hub.HfApi') as factory:
                api=factory.return_value;api.repo_info.return_value.sha='head-sha';api.list_repo_files.return_value=[]
                send_shard('example/portraits',True,path,'data/train/batch.parquet')
                call=api.create_commit.call_args
                self.assertEqual(call.kwargs['parent_commit'],'head-sha')
                self.assertEqual([op.path_in_repo for op in call.kwargs['operations']],['data/train/batch.parquet','README.md'])

    def test_missing_dataset_is_created_before_reads_or_uploads(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'batch.parquet';path.write_bytes(b'shard')
            created=[]
            with patch('huggingface_hub.HfApi') as factory:
                api=factory.return_value
                api.create_repo.side_effect=lambda *args,**kwargs:created.append(args[0])
                def repo_info(*args,**kwargs):
                    self.assertEqual(created,['lambdaWalker/ds.photo-id'])
                    return SimpleNamespace(sha='new-repo-head')
                api.repo_info.side_effect=repo_info
                api.list_repo_files.return_value=[]
                send_shard('lambdaWalker/ds.photo-id',True,path,'data/train/batch.parquet')
                api.create_repo.assert_called_once_with('lambdaWalker/ds.photo-id',repo_type='dataset',private=True,exist_ok=True)
                self.assertEqual(api.method_calls[0][0],'create_repo')
                api.create_commit.assert_called_once()

    def test_missing_login_explains_how_to_create_dataset(self):
        from huggingface_hub.errors import LocalTokenNotFoundError
        with patch('huggingface_hub.HfApi') as factory:
            api=factory.return_value
            api.create_repo.side_effect=LocalTokenNotFoundError('No saved login')
            with self.assertRaisesRegex(RuntimeError,'hf auth login'):
                send_shard('lambdaWalker/ds.photo-id',True,Path('unused'),'data/train/batch.parquet')
            api.create_commit.assert_not_called()

    def test_refuses_older_dataset_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'batch.parquet';path.write_bytes(b'shard')
            with patch('huggingface_hub.HfApi') as factory:
                api=factory.return_value;api.list_repo_files.return_value=['legacy.parquet']
                with self.assertRaisesRegex(ValueError,'dedicated empty'):
                    send_shard('example/portraits',True,path,'data/train/batch.parquet')
                api.create_commit.assert_not_called()
