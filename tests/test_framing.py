import copy
from pathlib import Path
import tempfile
import unittest

from generation_session import Session
from photo_id_generator import FRAMING, LEGACY_FRAMING, compose_prompt
from test_generation import CONFIG, PNG


class FramingTests(unittest.TestCase):
    def test_old_prompt_gets_leading_composition_without_duplicate_suffix(self):
        prompt = compose_prompt(f'A fictional adult wearing a scarf. {LEGACY_FRAMING}')
        self.assertTrue(prompt.startswith(FRAMING))
        self.assertNotIn(LEGACY_FRAMING, prompt)
        self.assertIn('wearing a scarf', prompt)
        self.assertEqual(compose_prompt(prompt), prompt)

    def test_resume_updates_only_unsent_prompts_without_an_original(self):
        with tempfile.TemporaryDirectory() as root:
            config = copy.deepcopy(CONFIG)
            session = Session(config, Path(root))
            old = f'Fictional portrait. {LEGACY_FRAMING}'
            session.update(1, prompt=old, state='ready')
            session.update(2, prompt=old, state='ready', remote_id='submitted', remote_url='http://server')
            session.update(3, prompt=old, state='ready')
            job = session.db.execute('SELECT * FROM jobs WHERE id=3').fetchone()
            image, prompt = session.paths(job)
            image.write_bytes(PNG)
            prompt.write_text(old)
            session.close()
            session = Session(config, Path(root))
            try:
                rows = session.db.execute('SELECT prompt FROM jobs ORDER BY id').fetchall()
                self.assertTrue(rows[0]['prompt'].startswith(FRAMING))
                self.assertEqual(rows[1]['prompt'], old)
                self.assertEqual(rows[2]['prompt'], old)
                self.assertEqual(prompt.read_text(), old)
            finally:
                session.close()
