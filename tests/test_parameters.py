import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from generation_session import Session, Pipeline
from test_generation import CONFIG, PNG, until


class ParametersTests(unittest.IsolatedAsyncioTestCase):
    async def test_exact_sample_and_execution_survive_restart(self):
        with tempfile.TemporaryDirectory() as root:
            config = copy.deepcopy(CONFIG)
            config['generation']['samples'] = 1
            session = Session(config, Path(root))
            sample = json.loads(session.next('pending')['parameters'])['sample']
            pipeline = Pipeline(session)
            with patch('generation_session.submit_image', return_value='original-job'), patch('generation_session.submit_background', return_value='bg-job'), patch('generation_session.wait_image', return_value=PNG):
                pipeline.start()
                await until(lambda: session.counts().get('done') == 1)
                await pipeline.stop()
            path = session.output / 'parameters/photoId_00001.json'
            data = json.loads(path.read_text())
            self.assertEqual(data['sample'], sample)
            self.assertEqual(data['sample']['age'], sample['age'])
            self.assertIn('clothing', data['sample'])
            self.assertIsInstance(data['prompt_seed'], int)
            self.assertEqual(data['image_workflow']['458']['inputs']['seed'], data['image_seed'])
            self.assertEqual(data['image_workflow']['452']['inputs']['prompt'], data['prompt'])
            self.assertEqual(data['prompt'], (session.output / data['files']['prompt']).read_text())
            self.assertEqual(data['background_removal']['workflow']['3']['class_type'], 'RemoveBackground')
            self.assertEqual(data['prompt_finalization']['result'], 'template')
            session.close()
            # Code/config changes must never resample already saved subject parameters.
            with patch('generation_session.prepare_prompt', side_effect=AssertionError('must not resample')):
                session = Session(config, Path(root))
            try:
                self.assertEqual(json.loads(path.read_text()), data)
            finally:
                session.close()

    async def test_legacy_image_exports_unknown_traits_without_resampling(self):
        with tempfile.TemporaryDirectory() as root:
            config = copy.deepcopy(CONFIG)
            session = Session(config, Path(root))
            job = session.next('pending')
            image, prompt = session.paths(job)
            image.write_bytes(PNG)
            prompt.write_text('Saved legacy prompt')
            session.update(job['id'], parameters=None)
            session.close()
            with patch('generation_session.prepare_prompt', side_effect=AssertionError('must not resample')):
                session = Session(config, Path(root))
            try:
                data = json.loads((session.output / 'parameters/photoId_00001.json').read_text())
                self.assertIsNone(data['sample'])
                self.assertIsNone(data['prompt_seed'])
                self.assertEqual(data['provenance'], 'legacy_partial')
                self.assertNotIn('image_workflow', data)
                self.assertEqual(data['prompt'], 'Saved legacy prompt')
            finally:
                session.close()

    async def test_import_without_journal_does_not_attach_new_sample_to_old_image(self):
        with tempfile.TemporaryDirectory() as root:
            output = Path(root) / 'output'
            (output / 'original').mkdir(parents=True)
            (output / 'prompts').mkdir()
            (output / 'original/photoId_00001.png').write_bytes(PNG)
            (output / 'prompts/photoId_00001.txt').write_text('Imported prompt')
            session = Session(copy.deepcopy(CONFIG), Path(root))
            try:
                data = json.loads((output / 'parameters/photoId_00001.json').read_text())
                self.assertIsNone(data['sample'])
                self.assertIsNone(data['image_seed'])
                self.assertEqual(data['draft_prompt'], '')
                self.assertEqual(data['prompt'], 'Imported prompt')
            finally:
                session.close()
