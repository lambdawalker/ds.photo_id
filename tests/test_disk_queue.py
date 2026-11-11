import asyncio
import copy
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from generation_session import Session, Pipeline
from test_generation import CONFIG, PNG, until


class DiskQueueTests(unittest.IsolatedAsyncioTestCase):
    async def test_prompts_finish_and_are_saved_while_first_image_is_blocked(self):
        config=copy.deepcopy(CONFIG)
        config['generation']['prompt_queue_size']=None
        entered=threading.Event();release=threading.Event()
        def wait(*args):
            entered.set()
            if not release.wait(5):raise TimeoutError('test timed out')
            return PNG
        with tempfile.TemporaryDirectory() as tmp:
            session=Session(config,Path(tmp));pipeline=Pipeline(session)
            with patch('generation_session.submit_image',return_value='image'),patch('generation_session.submit_background',return_value='background'),patch('generation_session.wait_image',side_effect=wait):
                pipeline.start()
                try:
                    await until(lambda: entered.is_set() and session.counts().get('ready')==4)
                    self.assertEqual(session.counts().get('rendering'),1)
                    for i in range(1,6):
                        stem=f'photoId_{i:05d}'
                        prompt=(session.output/'prompts'/f'{stem}.txt').read_text()
                        metadata=json.loads((session.output/'parameters'/f'{stem}.json').read_text())
                        self.assertIn('age',metadata)
                        self.assertNotIn('prompt',metadata)
                        self.assertTrue((session.output/'draft_prompts'/f'{stem}.txt').is_file())
                        self.assertTrue(prompt.strip())
                    pipeline.pause()
                finally:
                    release.set()
                    await pipeline.stop()
            saved=session.next('ready')['prompt']
            session.close()
            session=Session(config,Path(tmp))
            self.assertEqual(session.next('ready')['prompt'],saved)
            session.close()
