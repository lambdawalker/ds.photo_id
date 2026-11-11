import asyncio
import copy
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from filelock import Timeout
from textual.widgets import Static

from generation_session import Pipeline, Session
from generation_ui import GenerationApp
from photo_id_generator import ComfyGenerationError

import struct
import zlib

def png_fixture():
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 6, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(b'\x00\xff\x00\x00\x80')) + chunk(b'IEND', b''))

PNG = png_fixture()
CONFIG = {
    'generation': {'samples': 5, 'seed': 42, 'output_dir': 'output', 'prompt_queue_size': 2},
    'llm': {'enabled': False, 'url': 'http://llm.test/v1'},
    'comfyui': {'url': 'http://comfy.test', 'timeout_seconds': 1},
}


async def until(predicate):
    async def wait():
        while not predicate():
            await asyncio.sleep(.01)
    await asyncio.wait_for(wait(), 4)


class PipelineTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.background_patch = patch('generation_session.submit_background', return_value='bg-job')
        self.background_patch.start()
        self.addCleanup(self.background_patch.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.config = copy.deepcopy(CONFIG)
        self.session = Session(self.config, self.root)
        self.pipeline = Pipeline(self.session)

    async def asyncTearDown(self):
        await self.pipeline.stop()
        self.session.close()
        self.temp.cleanup()

    async def test_parallel_pause_and_resume_in_new_session(self):
        llm_second = threading.Event()
        image_first = threading.Event()
        release = threading.Event()
        count = 0

        def llm(draft, required, config):
            nonlocal count
            count += 1
            if count == 2:
                llm_second.set()
                if not release.wait(4):
                    raise TimeoutError('test release timed out')
            return draft

        def image(*args):
            image_first.set()
            if not release.wait(4):
                raise TimeoutError('test release timed out')
            return PNG

        with patch('generation_session.finalize_prompt', side_effect=llm), patch('generation_session.submit_image', return_value='job-1'), patch('generation_session.wait_image', side_effect=image):
            self.pipeline.start()
            try:
                await until(lambda: llm_second.is_set() and image_first.is_set())
                self.assertTrue(all(self.pipeline.active.values()), 'LLM and Comfy must overlap')
                self.pipeline.pause()
            finally:
                release.set()
            await until(lambda: not any(self.pipeline.active.values()))
            self.assertEqual(self.session.counts(), {'done': 1, 'pending': 3, 'ready': 1})
            await self.pipeline.stop()
        saved = self.session.next('ready')['prompt']
        self.session.close()
        self.session = Session(self.config, self.root)
        self.assertEqual(saved, self.session.next('ready')['prompt'])
        self.pipeline = Pipeline(self.session)
        with patch('generation_session.submit_image', return_value='job-2') as submit, patch('generation_session.wait_image', return_value=PNG):
            self.pipeline.start()
            await until(lambda: self.session.counts().get('done') == 5)
            self.assertEqual(submit.call_count, 4)
            self.assertEqual(len(list((self.session.output / 'original').glob('*.png'))), 5)
            self.assertEqual(len(list((self.session.output / 'prompts').glob('*.txt'))), 5)

    async def test_save_exit_drains_inflight_without_dispatching_more(self):
        entered = threading.Event()
        release = threading.Event()
        def image(*args):
            entered.set()
            release.wait(4)
            return PNG
        with patch('generation_session.submit_image', return_value='active') as submit, patch('generation_session.wait_image', side_effect=image):
            self.pipeline.start()
            try:
                await until(entered.is_set)
                stopping = asyncio.create_task(self.pipeline.stop())
                await asyncio.sleep(.03)
                self.assertFalse(stopping.done())
            finally:
                release.set()
            await stopping
            self.assertEqual(submit.call_count, 1)
            self.assertEqual(self.session.counts()['done'], 1)

    async def test_queue_is_bounded(self):
        release = threading.Event()
        def image(*args):
            release.wait(4)
            return PNG
        with patch('generation_session.submit_image', return_value='queued'), patch('generation_session.wait_image', side_effect=image):
            self.pipeline.start()
            try:
                await until(lambda: self.session.counts().get('ready') == 2)
                await asyncio.sleep(.05)
                self.assertEqual(self.session.counts().get('pending'), 2)
                self.pipeline.pause()
            finally:
                release.set()
            await self.pipeline.stop()

    async def test_timeout_retry_uses_saved_remote_id(self):
        with patch('generation_session.submit_image', return_value='durable-id') as submit, patch('generation_session.wait_image', side_effect=TimeoutError('still running')):
            self.pipeline.start()
            await until(lambda: self.session.counts().get('failed') == 1)
            self.assertTrue(self.pipeline.paused)
            await self.pipeline.stop()
            self.assertEqual(submit.call_count, 1)
        self.session.close()
        self.session = Session(self.config, self.root)
        self.pipeline = Pipeline(self.session)
        self.pipeline.retry()
        self.assertEqual(self.session.next('ready')['remote_id'], 'durable-id')
        first = self.session.next('ready')
        with patch('generation_session.submit_image') as submit, patch('generation_session.wait_image', return_value=PNG) as wait:
            await self.pipeline._image(first)
            submit.assert_not_called()
            self.assertEqual(wait.call_args_list[0].args[0], 'durable-id')

    async def test_resubmit_lost_job_preserves_prompt_and_seed(self):
        self.session.update(1, prompt='Exact prompt', state='failed', remote_id='lost', remote_url='http://old')
        before = self.session.next('failed')
        self.pipeline.retry(resubmit=True)
        job = self.session.next('ready')
        self.assertIsNone(job['remote_id'])
        self.assertEqual(job['prompt'], before['prompt'])
        self.assertEqual(job['image_seed'], before['image_seed'])

    async def test_background_failure_preserves_original_and_retries_only_removal(self):
        def wait(remote_id, *args):
            if remote_id == 'bg-job':
                raise TimeoutError('background busy')
            return PNG
        with patch('generation_session.submit_image', return_value='original-job'), patch('generation_session.wait_image', side_effect=wait):
            self.pipeline.start()
            await until(lambda: self.session.counts().get('failed') == 1)
            await self.pipeline.stop()
        job = self.session.next('failed')
        self.assertTrue(self.session.paths(job)[0].is_file())
        self.assertFalse(self.session.transparent_path(job).exists())
        self.session.close()
        self.session = Session(self.config, self.root)
        self.pipeline = Pipeline(self.session)
        self.pipeline.retry()
        job = self.session.next('ready')
        with patch('generation_session.submit_image') as submit, patch('generation_session.submit_background') as bg, patch('generation_session.wait_image', return_value=PNG):
            await self.pipeline._image(job)
            submit.assert_not_called()
            bg.assert_not_called()
        self.assertEqual(self.session.transparent_path(job).read_bytes(), PNG)

    async def test_legacy_folders_migrate_and_queue_missing_transparency(self):
        self.session.close()
        output = self.root / 'output'
        (output / 'original').rename(output / 'img')
        (output / 'prompts').rename(output / 'prompt')
        (output / 'img/photoId_00001.png').write_bytes(PNG)
        (output / 'prompt/photoId_00001.txt').write_text('Legacy prompt')
        self.session = Session(self.config, self.root)
        self.pipeline = Pipeline(self.session)
        self.assertFalse((output / 'img').exists())
        self.assertFalse((output / 'prompt').exists())
        job = self.session.next('ready')
        self.assertEqual(job['prompt'], 'Legacy prompt')
        self.assertEqual(self.session.paths(job)[0].read_bytes(), PNG)

    async def test_nested_folders_migrate_without_regeneration(self):
        self.session.close()
        output = self.root / 'output'
        (output / 'images').mkdir()
        (output / 'original').rename(output / 'images/original')
        (output / 'transparent').rename(output / 'images/transparent')
        for variant in ('original', 'transparent'):
            (output / 'images' / variant / 'photoId_00001.png').write_bytes(PNG)
        (output / 'prompts/photoId_00001.txt').write_text('Saved prompt')
        self.session = Session(self.config, self.root)
        self.pipeline = Pipeline(self.session)
        self.assertFalse((output / 'images').exists())
        self.assertEqual(self.session.counts()['done'], 1)
        for variant in ('original', 'transparent'):
            self.assertEqual((output / variant / 'photoId_00001.png').read_bytes(), PNG)

    async def test_terminal_failure_clears_remote_id(self):
        with patch('generation_session.submit_image', return_value='bad-id'), patch('generation_session.wait_image', side_effect=ComfyGenerationError('bad workflow')):
            self.pipeline.start()
            await until(lambda: self.session.counts().get('failed') == 1)
            self.assertIsNone(self.session.next('failed')['remote_id'])

    async def test_changed_batch_rejected_and_lock_released(self):
        with self.assertRaises(Timeout):
            Session(self.config, self.root)
        self.session.close()
        different = copy.deepcopy(self.config)
        different['generation']['seed'] = 1
        with self.assertRaisesRegex(ValueError, 'Batch size/seed'):
            Session(different, self.root)
        self.session = Session(self.config, self.root)
        self.pipeline = Pipeline(self.session)

    async def test_crash_recovery_retains_prompt_and_remote_id(self):
        self.session.update(1, prompt='Saved exact prompt', state='rendering', remote_id='remote', remote_url='http://original')
        self.session.update(2, state='prompting')
        self.session.close()
        self.session = Session(self.config, self.root)
        self.pipeline = Pipeline(self.session)
        job = self.session.next('ready')
        self.assertEqual((job['prompt'], job['remote_id']), ('Saved exact prompt', 'remote'))
        self.assertEqual(self.session.next('pending')['id'], 2)
        with patch('generation_session.wait_image', return_value=PNG) as wait:
            await self.pipeline._image(job)
        self.assertEqual(wait.call_args_list[0].args[2]['url'], 'http://original')

    async def test_completed_files_reconcile_after_interrupted_commit(self):
        job = self.session.next('pending')
        image, prompt = self.session.paths(job)
        image.write_bytes(PNG)
        prompt.write_text('Saved prompt', encoding='utf-8')
        self.session.close()
        self.session = Session(self.config, self.root)
        self.pipeline = Pipeline(self.session)
        self.assertEqual(self.session.counts()['ready'], 1)


class UITests(unittest.IsolatedAsyncioTestCase):
    async def test_panels_pause_resume_and_exit(self):
        with tempfile.TemporaryDirectory() as root, patch('generation_session.submit_background', return_value='bg-ui'), patch('generation_session.submit_image', return_value='ui-job'), patch('generation_session.wait_image', return_value=PNG):
            app = GenerationApp(copy.deepcopy(CONFIG), Path(root))
            async with app.run_test(size=(120, 38)) as pilot:
                await until(lambda: app.pipeline is not None)
                await until(lambda: app.session.counts().get('done') == 5)
                await pilot.pause()
                self.assertEqual(len(app.query('ProgressBar')), 3)
                await pilot.press('space')
                self.assertTrue(app.pipeline.paused)
                await pilot.press('space')
                self.assertFalse(app.pipeline.paused)
                await pilot.resize_terminal(80, 48)
                self.assertTrue(app.screen.has_class('compact'))
                await pilot.press('q')
                self.assertTrue(app.closing)

    async def test_startup_error_is_shown(self):
        config = copy.deepcopy(CONFIG)
        config['generation']['samples'] = 0
        with tempfile.TemporaryDirectory() as root:
            app = GenerationApp(config, Path(root))
            async with app.run_test() as pilot:
                await pilot.pause()
                self.assertIn('positive integer', str(app.query_one('#summary', Static).render()))
                await pilot.press('q')
