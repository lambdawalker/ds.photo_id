import json
import unittest
from unittest.mock import patch
from jinja2 import Environment, FileSystemLoader
from photo_id_generator import ROOT, prepare_prompt, finalize_prompt, build_image_graph
from id_data.metadata import get_metadata


class FacialConditionTests(unittest.TestCase):
    def template(self):
        return Environment(loader=FileSystemLoader(ROOT / 'res')).get_template('photoId.j2')

    def test_pose_is_level_and_glasses_can_be_disabled(self):
        for _ in range(100):
            metadata = get_metadata('woman', diversity={'glasses_probability': 0})
            self.assertIn('level', metadata['head_tilt'])
            self.assertNotIn('~', metadata['head_tilt'])
            self.assertEqual(metadata['glasses'], '')
            self.assertIn('no eyeglasses', metadata['eyewear_instruction'])

    def test_each_condition_is_rendered_and_preserved(self):
        from id_data.diversity import DEFAULTS
        for kind in DEFAULTS['facial_conditions']:
            rates = {name: float(name == kind) for name in DEFAULTS['facial_conditions']}
            draft, required, data = prepare_prompt(55, 72, self.template(), True,
                diversity={'facial_conditions': rates})
            self.assertEqual(data['facial_condition']['type'], kind)
            for phrase in required:
                self.assertIn(phrase.casefold(), draft.casefold())
            self.assertIn(data['facial_condition']['description'], required)
            self.assertIn(data['ancestry'], required)
            self.assertIn(data['ancestry'], draft)
            self.assertEqual(data['race_ethnicity'], data['ancestry'])

    def test_cataracts_are_explicit_not_automatically_blindness(self):
        for seed in range(30):
            draft, required, data = prepare_prompt(80, seed, self.template(), True,
                diversity={'blindness_probability': 0, 'cataracts_by_age': {'18_39': 1, '40_59': 1, '60_74': 1, '75_plus': 1}})
            self.assertNotEqual(data['eyes']['cataracts']['profile'], 'none')
            self.assertEqual(data['eyes']['vision']['profile'], 'unspecified')
            self.assertIn(data['eyes']['cataracts']['description'], required)
            self.assertIn('cataract', draft)

    def test_no_glasses_negative_conditioning_does_not_block_requested_glasses(self):
        graph = json.loads((ROOT / 'res/qwen_image_2_1_api.json').read_text())
        clear = build_image_graph(graph, 'no eyeglasses or sunglasses; eyes unobstructed', 1, 'test')
        self.assertIn('eyeglasses', clear['452']['inputs']['negative_prompt'])
        wearing = build_image_graph(graph, 'Wearing round glasses.', 1, 'test')
        self.assertNotIn('eyeglasses', wearing['452']['inputs']['negative_prompt'])

    def test_long_complete_rewrite_is_accepted(self):
        draft, required = prepare_prompt(55, 72, self.template())
        candidate = draft + ' ' + ' '.join(['Natural portrait detail.'] * 20)
        llm = {'enabled': True, 'api': 'openai', 'url': 'http://example', 'model': 'local', 'timeout_seconds': 5}
        with patch('photo_id_generator.request_json', return_value={'choices': [{'message': {'content': candidate}}]}):
            self.assertEqual(finalize_prompt(draft, required, llm), candidate)

    def test_invalid_probabilities_are_rejected(self):
        from id_data.diversity import settings
        for value in (-1, 2, float('nan'), True):
            with self.assertRaises(ValueError):
                settings({'glasses_probability': value})
        with self.assertRaises(ValueError):
            settings({'facial_conditions': {'cleft_lip': .9, 'down_syndrome': .9}})

    def test_shipped_yaml_and_token_budget_are_used(self):
        import yaml
        config = yaml.safe_load((ROOT / 'config.yaml').read_text())
        draft, required, data = prepare_prompt(65, 123, self.template(), True,
            diversity=config['generation']['diversity'])
        self.assertEqual(data['diversity_settings']['glasses_probability'], .05)
        self.assertEqual(config['llm']['max_output_tokens'], 4096)
        with patch('photo_id_generator.request_json', return_value={'output': [{'type': 'message', 'content': draft}]}) as request:
            self.assertEqual(finalize_prompt(draft, required, config['llm']), draft)
            self.assertEqual(request.call_args.args[2]['max_output_tokens'], 4096)

    def test_openai_budget_and_truncated_response(self):
        llm = {'enabled': True, 'api': 'openai', 'url': 'http://example', 'model': 'local', 'timeout_seconds': 5, 'max_output_tokens': 6000}
        with patch('photo_id_generator.request_json', return_value={'choices': [{'finish_reason': 'length', 'message': {'content': 'A required trait.'}}]}) as request:
            self.assertEqual(finalize_prompt('Draft includes required trait.', ['required trait'], llm), 'Draft includes required trait.')
            self.assertEqual(request.call_args.args[2]['max_tokens'], 6000)
