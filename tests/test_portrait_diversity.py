import unittest
from jinja2 import Environment, FileSystemLoader
from photo_id_generator import ROOT, FRAMING, prepare_prompt


class PortraitDiversityTests(unittest.TestCase):
    def test_new_traits_survive_rendering_and_are_required_for_llm(self):
        template = Environment(loader=FileSystemLoader(ROOT / 'res')).get_template('photoId.j2')
        expressions, builds, vision_profiles, birthmarks = set(), set(), set(), set()
        for seed in range(400):
            draft, required, sample = prepare_prompt(42, seed, template, include_data=True)
            self.assertIn('build', sample, 'Visible build variation must be sampled')
            phrases = [sample['metadata']['expression'], sample['build']['description'],
                       sample['skin']['birthmark']['description'], sample['eyes']['vision']['description']]
            for phrase in filter(None, phrases):
                self.assertIn(phrase.casefold(), draft.casefold())
                self.assertIn(phrase, required)
            for phrase in required:
                self.assertIn(phrase.casefold(), draft.casefold())
            expressions.add(sample['metadata']['expression'])
            builds.add(sample['build']['category'])
            vision_profiles.add(sample['eyes']['vision']['profile'])
            birthmarks.add(sample['skin']['birthmark']['type'])
            self.assertIn('nose_width', sample['face'])
            self.assertIn('nostrils', sample['face'])
        self.assertGreaterEqual(len(expressions), 12)
        self.assertGreaterEqual(len(builds), 6)
        self.assertGreaterEqual(len(vision_profiles), 4)
        self.assertGreaterEqual(len(birthmarks), 4)

    def test_fixed_framing_does_not_force_eye_contact(self):
        self.assertNotIn('Eyes look directly', FRAMING)

    def test_other_sampled_visual_details_reach_prompt_and_llm_constraints(self):
        template = Environment(loader=FileSystemLoader(ROOT / 'res')).get_template('photoId.j2')
        for seed in range(100):
            draft, required, data = prepare_prompt(65, seed, template, include_data=True)
            phrases = [data['hair']['stray_hair'], data['clothing']['condition']]
            phrases += [data['metadata'][key] for key in (
                'lens', 'lighting', 'quality_profile', 'motion_hint', 'head_tilt',
                'head_yaw', 'shoulders', 'grooming', 'makeup', 'jewelry', 'body_detail',
                'hat', 'extra_headwear')]
            for phrase in filter(None, phrases):
                self.assertIn(phrase.casefold(), draft.casefold())
                self.assertIn(phrase, required)
