import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch, MagicMock

from filelock import FileLock, Timeout


class ResetDatasetTests(unittest.TestCase):
    def config(self):
        return {'generation': {'output_dir': 'dataset/idPhoto'},
                'huggingface': {'repo_id': 'lambdaWalker/ds.photo-id'}}

    def make_output(self, root):
        output = Path(root) / 'dataset/idPhoto'
        output.mkdir(parents=True)
        (output / 'session.sqlite3').write_bytes(b'journal')
        (output / 'original').mkdir()
        (output / 'original/test.webp').write_bytes(b'image')
        return output

    def test_clears_remote_then_local_preserving_card_and_code(self):
        from reset_dataset import reset_dataset
        with tempfile.TemporaryDirectory() as root:
            output = self.make_output(root)
            api = MagicMock()
            api.repo_info.return_value = SimpleNamespace(sha='head')
            api.list_repo_files.side_effect = [['README.md', '.gitattributes', 'data/train/one.parquet'], ['README.md', '.gitattributes']]
            api.list_repo_refs.return_value = SimpleNamespace(tags=[], branches=[SimpleNamespace(name='main')])
            with patch('reset_dataset.HfApi', return_value=api), patch('reset_dataset.hf_hub_download') as download:
                card = Path(root) / 'card.md'
                card.write_text('live_upload_layout: ds-photo-id-v2')
                download.return_value = str(card)
                reset_dataset(self.config(), Path(root), progress=lambda message: None)
            operations = api.create_commit.call_args.kwargs['operations']
            self.assertEqual([op.path_in_repo for op in operations], ['data/train/one.parquet'])
            self.assertEqual(api.create_commit.call_args.kwargs['parent_commit'], 'head')
            api.super_squash_history.assert_called_once()
            self.assertEqual([p.name for p in output.iterdir()], ['session.lock'])
            self.assertTrue(card.exists())

    def test_remote_failure_retains_local_records(self):
        from reset_dataset import reset_dataset
        with tempfile.TemporaryDirectory() as root:
            output = self.make_output(root)
            with patch('reset_dataset.HfApi') as factory:
                factory.return_value.repo_info.side_effect = RuntimeError('offline')
                with self.assertRaisesRegex(RuntimeError, 'offline'):
                    reset_dataset(self.config(), Path(root), progress=lambda message: None)
            self.assertTrue((output / 'session.sqlite3').exists())

    def test_running_generator_blocks_reset_before_remote_requests(self):
        from reset_dataset import reset_dataset
        with tempfile.TemporaryDirectory() as root:
            output = self.make_output(root)
            with FileLock(output / 'session.lock', timeout=0):
                with patch('reset_dataset.HfApi') as factory:
                    with self.assertRaises(Timeout):
                        reset_dataset(self.config(), Path(root), progress=lambda message: None)
                    factory.assert_not_called()

    def test_refuses_source_directory_as_output(self):
        from reset_dataset import reset_dataset
        with tempfile.TemporaryDirectory() as root:
            config = self.config()
            config['generation']['output_dir'] = '.'
            with patch('reset_dataset.HfApi') as factory:
                with self.assertRaises(ValueError):
                    reset_dataset(config, Path(root), progress=lambda message: None)
                factory.assert_not_called()

    def test_unrelated_repository_is_not_deleted(self):
        from reset_dataset import reset_dataset
        with tempfile.TemporaryDirectory() as root:
            output = self.make_output(root)
            api = MagicMock()
            api.repo_info.return_value = SimpleNamespace(sha='head')
            api.list_repo_refs.return_value = SimpleNamespace(tags=[], branches=[SimpleNamespace(name='main')])
            card = Path(root) / 'card.md'
            card.write_text('Unrelated dataset')
            with patch('reset_dataset.HfApi', return_value=api), patch('reset_dataset.hf_hub_download', return_value=str(card)):
                with self.assertRaisesRegex(ValueError, 'marker'):
                    reset_dataset(self.config(), Path(root), progress=lambda message: None)
            api.create_commit.assert_not_called()
            api.super_squash_history.assert_not_called()
            self.assertTrue((output / 'session.sqlite3').exists())

    def test_history_failure_retains_local_session(self):
        from reset_dataset import reset_dataset
        with tempfile.TemporaryDirectory() as root:
            output = self.make_output(root)
            api = MagicMock()
            api.repo_info.return_value = SimpleNamespace(sha='head')
            api.list_repo_refs.return_value = SimpleNamespace(tags=[], branches=[SimpleNamespace(name='main')])
            api.list_repo_files.return_value = ['README.md', '.gitattributes']
            api.super_squash_history.side_effect = RuntimeError('squash failed')
            card = Path(root) / 'card.md'
            card.write_text('live_upload_layout: ds-photo-id-v1')
            with patch('reset_dataset.HfApi', return_value=api), patch('reset_dataset.hf_hub_download', return_value=str(card)):
                with self.assertRaisesRegex(RuntimeError, 'squash failed'):
                    reset_dataset(self.config(), Path(root), progress=lambda message: None)
            self.assertTrue((output / 'session.sqlite3').exists())

    def test_unexpected_local_files_prevent_remote_deletion(self):
        from reset_dataset import reset_dataset
        with tempfile.TemporaryDirectory() as root:
            output = self.make_output(root)
            (output / 'keep.txt').write_text('unrelated')
            with patch('reset_dataset.HfApi') as factory:
                with self.assertRaisesRegex(ValueError, 'unexpected files'):
                    reset_dataset(self.config(), Path(root), progress=lambda message: None)
                factory.assert_not_called()
