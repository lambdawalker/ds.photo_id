import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from generation_session import Session, Pipeline
from incremental_upload import LiveUploader, ordered_shard_path, order_uploaded_batches, CARD
from test_incremental_upload import config, complete


class UploadOrderTests(unittest.TestCase):
    def test_sequence_controls_sorting_instead_of_random_uuid(self):
        with tempfile.TemporaryDirectory() as tmp:
            session=Session(config(),Path(tmp));complete(session,[1,2,3]);u=LiveUploader(Pipeline(session))
            with patch('incremental_upload.uuid.uuid4') as uuid:
                uuid.return_value.hex='f'*32
                first=u.prepare_batch(u.unassigned())
                with session.db:
                    session.db.execute("UPDATE upload_batches SET status='uploaded' WHERE id=?",(first['id'],))
                uuid.return_value.hex='0'*32
                second=u.prepare_batch(u.unassigned())
            self.assertLess(first['remote_path'],second['remote_path'])
            self.assertIn('-00000001-',first['remote_path'])
            self.assertIn('-00000002-',second['remote_path'])
            session.close()

    def test_repair_is_atomic_and_recovers_from_lost_ack(self):
        from huggingface_hub import CommitOperationCopy, CommitOperationDelete
        with tempfile.TemporaryDirectory() as tmp:
            session=Session(config(),Path(tmp));complete(session,[1,2]);u=LiveUploader(Pipeline(session))
            batch=u.prepare_batch(u.unassigned())
            legacy=f'data/train/{u.session_id}-{batch["id"]}.parquet'
            target=ordered_shard_path(u.session_id,1,batch['id'])
            with session.db:
                session.db.execute("UPDATE upload_batches SET status='uploaded',remote_path=? WHERE id=?",(legacy,batch['id']))
            card=Path(tmp)/'card.md';card.write_text(CARD)
            remote={legacy:b'unchanged-image-and-row-bytes'}
            def commit(*args,**kwargs):
                ops=kwargs['operations']
                self.assertIsInstance(ops[0],CommitOperationCopy)
                self.assertIsInstance(ops[1],CommitOperationDelete)
                remote[ops[0].path_in_repo]=remote[ops[0].src_path_in_repo]
                del remote[ops[1].path_in_repo]
                raise TimeoutError('server committed but response lost')
            with patch('huggingface_hub.HfApi') as factory,patch('huggingface_hub.hf_hub_download',return_value=str(card)):
                api=factory.return_value;api.repo_info.return_value.sha='head'
                api.list_repo_files.side_effect=lambda *args,**kwargs:list(remote)
                api.create_commit.side_effect=commit
                with self.assertRaises(TimeoutError):order_uploaded_batches(u,lambda _:None)
                self.assertEqual(remote,{target:b'unchanged-image-and-row-bytes'})
                api.create_commit.reset_mock();api.create_commit.side_effect=None
                self.assertEqual(order_uploaded_batches(u,lambda _:None),1)
                api.create_commit.assert_not_called()
                self.assertEqual(session.db.execute('SELECT remote_path FROM upload_batches').fetchone()[0],target)
                self.assertEqual(order_uploaded_batches(u,lambda _:None),0)
            session.close()

    def test_repair_refuses_conflicting_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            session=Session(config(),Path(tmp));complete(session,[1]);u=LiveUploader(Pipeline(session));batch=u.prepare_batch(u.unassigned())
            legacy=f'data/train/{u.session_id}-{batch["id"]}.parquet'
            with session.db:
                session.db.execute("UPDATE upload_batches SET status='uploaded',remote_path=?",(legacy,))
            card=Path(tmp)/'card.md';card.write_text(CARD)
            with patch('huggingface_hub.HfApi') as factory,patch('huggingface_hub.hf_hub_download',return_value=str(card)):
                api=factory.return_value;api.list_repo_files.return_value=[legacy,batch['remote_path']]
                with self.assertRaisesRegex(ValueError,'Both source and ordered'):
                    order_uploaded_batches(u,lambda _:None)
                api.create_commit.assert_not_called()
            session.close()
