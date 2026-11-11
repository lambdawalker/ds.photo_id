import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from generation_session import Session, Pipeline
from test_generation import CONFIG, PNG, until


class ParametersTests(unittest.IsolatedAsyncioTestCase):
    async def test_selected_values_metadata_and_draft_survive_restart(self):
        with tempfile.TemporaryDirectory() as root:
            config = copy.deepcopy(CONFIG)
            config['generation']['samples'] = 1
            session = Session(config, Path(root))
            sampled = session.next('pending')
            sample = json.loads(sampled['parameters'])['sample']
            draft = sampled['draft']
            pipeline = Pipeline(session)
            with patch('generation_session.submit_image', return_value='original-job'), patch('generation_session.submit_background', return_value='bg-job'), patch('generation_session.wait_image', return_value=PNG):
                pipeline.start()
                await until(lambda: session.counts().get('done') == 1)
                await pipeline.stop()
            path = session.output / 'parameters/photoId_00001.json'
            data = json.loads(path.read_text())
            self.assertEqual(data['age'], sample['age'])
            self.assertEqual(data['skin']['tone'], sample['skin']['tone'])
            self.assertEqual(data['clothing']['pieces'], sample['clothing']['pieces'])
            self.assertNotIn('sample', data)
            self.assertNotIn('diversity_settings', data)
            self.assertNotIn('id', data)
            self.assertNotIn('draft_prompt', data)
            metadata_path = session.output / 'metadata/photoId_00001.json'
            metadata = json.loads(metadata_path.read_text())
            self.assertEqual(set(metadata), {'id', 'image_seed', 'prompt_seed', 'provenance', 'image_requested_at', 'prompt_finalization'})
            self.assertIsInstance(metadata['prompt_seed'], int)
            self.assertEqual(metadata['prompt_finalization']['result'], 'template')
            self.assertTrue(metadata['image_requested_at'])
            self.assertEqual((session.output / 'draft_prompts/photoId_00001.txt').read_text(), draft)
            self.assertNotIn('workflow', path.read_text() + metadata_path.read_text())
            session.close()
            path.write_text(json.dumps({'sample': sample, 'image_workflow': {'old': 'flow'}}))
            with patch('generation_session.prepare_prompt', side_effect=AssertionError('must not resample')):
                session = Session(config, Path(root))
            try:
                self.assertEqual(json.loads(path.read_text()), data)
                self.assertEqual(json.loads(metadata_path.read_text()), metadata)
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
                self.assertEqual(json.loads((session.output / 'parameters/photoId_00001.json').read_text()), {})
                metadata = json.loads((session.output / 'metadata/photoId_00001.json').read_text())
                self.assertIsNone(metadata['prompt_seed'])
                self.assertEqual(metadata['provenance'], 'legacy_partial')
                self.assertEqual((session.output / 'prompts/photoId_00001.txt').read_text(), 'Saved legacy prompt')
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
                self.assertEqual(json.loads((output / 'parameters/photoId_00001.json').read_text()), {})
                metadata = json.loads((output / 'metadata/photoId_00001.json').read_text())
                self.assertIsNone(metadata['image_seed'])
                self.assertEqual((output / 'draft_prompts/photoId_00001.txt').read_text(), '')
            finally:
                session.close()
