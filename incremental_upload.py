"""Durable, idempotent Parquet batches for a dedicated Hugging Face dataset."""
import asyncio
from contextvars import ContextVar
import math
from io import BytesIO
import json
from pathlib import Path
import time
import uuid

from file_storage import atomic_write

_reporter = ContextVar('upload_progress_reporter', default=None)


def report(phase):
    callback = _reporter.get()
    if callback:
        callback(phase)


CARD = '''---
live_upload_layout: ds-photo-id-v1
configs:
- config_name: default
  data_files:
  - split: train
    path: data/train/*.parquet
---
# Synthetic ID portraits

Fictional Qwen portraits with transparent versions and generation parameters.
Rows are added in batches. Parameters describe intended inputs, not measured attributes.
The parameters column contains JSON text. Image bytes are embedded in Parquet shards.
'''


def make_shard(path, records):
    from datasets import Dataset, Features, Image, Value, disable_progress_bars
    disable_progress_bars()
    features = Features({'id': Value('string'), 'image': Image(), 'image_transparent': Image(),
                         'prompt': Value('string'), 'parameters': Value('string')})
    rows = []
    for record in records:
        metadata = json.loads(Path(record['parameters']).read_text(encoding='utf-8'))
        prompt = Path(record['prompt']).read_text(encoding='utf-8')
        if not prompt.strip() or metadata.get('prompt') != prompt:
            raise ValueError(f'Prompt/parameters mismatch: {record["id"]}')
        row = {'id': record['id'], 'prompt': prompt, 'parameters': json.dumps(metadata, ensure_ascii=False)}
        for name in ('image', 'image_transparent'):
            image = Path(record[name])
            row[name] = {'path': image.name, 'bytes': image.read_bytes()}
        rows.append(row)
    buffer = BytesIO()
    Dataset.from_list(rows, features=features).to_parquet(buffer)
    atomic_write(path, buffer.getvalue())


def send_shard(repo_id, private, path, remote_path):
    from huggingface_hub import HfApi, CommitOperationAdd, hf_hub_download
    from huggingface_hub.utils import disable_progress_bars
    disable_progress_bars()
    api = HfApi()
    from huggingface_hub.errors import HfHubHTTPError, LocalTokenNotFoundError
    report('Creating/checking dataset')
    try:
        api.create_repo(repo_id, repo_type='dataset', private=private, exist_ok=True)
    except LocalTokenNotFoundError as error:
        raise RuntimeError('Sign in once with `uv run --locked hf auth login` to create the dataset') from error
    except HfHubHTTPError as error:
        if error.response is not None and error.response.status_code in (401, 403):
            raise RuntimeError(
                f'Cannot create/access dataset {repo_id}. Run `uv run --locked hf auth login` '
                'with an account that has permission to create datasets in this namespace.'
            ) from error
        raise
    report('Checking repository layout')
    head = api.repo_info(repo_id, repo_type='dataset').sha
    files = api.list_repo_files(repo_id, repo_type='dataset', revision=head)
    operations = [CommitOperationAdd(path_in_repo=remote_path, path_or_fileobj=str(path))]
    if 'README.md' not in files:
        if any(name.endswith(('.parquet', '.csv', '.jsonl')) for name in files):
            raise ValueError('Use a dedicated empty dataset for incremental uploads')
        operations.append(CommitOperationAdd(path_in_repo='README.md', path_or_fileobj=CARD.encode()))
    else:
        card = Path(hf_hub_download(repo_id, 'README.md', repo_type='dataset', revision=head)).read_text(encoding='utf-8')
        if 'live_upload_layout: ds-photo-id-v1' not in card:
            raise ValueError('Choose a new repo_id: this dataset is not an incremental portrait dataset')
    report('Uploading shard and committing')
    api.create_commit(repo_id, repo_type='dataset', operations=operations,
                      commit_message=f'Add portrait batch {path.stem}', parent_commit=head)


class LiveUploader:
    def __init__(self, pipeline):
        self.pipeline, self.session = pipeline, pipeline.session
        self.config = self.session.config.get('huggingface', {})
        self.repo = self.config.get('repo_id', '')
        self.batch_size = self.config.get('batch_size', 10)
        self.interval = self.config.get('interval_seconds', 300)
        self.retry_delay = self.config.get('retry_seconds', 60)
        if not self.repo or '/' not in self.repo:
            raise ValueError('huggingface.repo_id must be owner/dataset')
        if not isinstance(self.batch_size, int) or self.batch_size < 1 or self.interval <= 0 or self.retry_delay <= 0:
            raise ValueError('Upload batch size and intervals must be positive')
        self.db = self.session.db
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS upload_batches (
                id TEXT PRIMARY KEY, repo TEXT NOT NULL, job_ids TEXT NOT NULL,
                remote_path TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending', error TEXT
            );
            CREATE TABLE IF NOT EXISTS upload_items (
                repo TEXT NOT NULL, job_id INTEGER NOT NULL, batch_id TEXT NOT NULL,
                PRIMARY KEY(repo, job_id)
            );
        ''')
        with self.db:
            self.db.execute('INSERT OR IGNORE INTO meta VALUES(?,?)', ('upload_session_id', uuid.uuid4().hex))
        self.session_id = self.db.execute("SELECT value FROM meta WHERE key='upload_session_id'").fetchone()['value']
        self.changed = asyncio.Event()
        self.stopping = False
        self.status, self.error, self.task = 'waiting', None, None
        self.phase = 'Waiting for completed portraits'
        self.current_batch = None
        self.batch_records = 0
        self.next_retry = 0
        (self.session.output / 'uploads').mkdir(exist_ok=True)

    def progress(self, phase):
        self.phase = phase
        self.pipeline.notify('upload', phase)

    def retry(self):
        self.next_retry = 0
        self.changed.set()

    def start(self):
        self.task = asyncio.create_task(self.run())

    async def stop(self):
        self.stopping = True
        self.changed.set()
        if self.task:
            await self.task

    def unassigned(self):
        return self.db.execute("SELECT id FROM jobs WHERE state='done' AND id NOT IN "
                               '(SELECT job_id FROM upload_items WHERE repo=?) ORDER BY id LIMIT ?',
                               (self.repo, self.batch_size)).fetchall()

    def snapshot(self):
        uploaded = self.db.execute("SELECT COUNT(*) FROM upload_items i JOIN upload_batches b ON b.id=i.batch_id "
                                   "WHERE i.repo=? AND b.status='uploaded'", (self.repo,)).fetchone()[0]
        return {'enabled': True, 'repo_id': self.repo, 'uploaded': uploaded,
                'pending': max(0, self.session.counts().get('done', 0)-uploaded),
                'status': self.status, 'error': self.error, 'phase': self.phase,
                'current_batch': self.current_batch, 'batch_records': self.batch_records,
                'retry_in_seconds': max(0, math.ceil(self.next_retry-time.monotonic())) if self.status == 'retrying' else 0}

    def next_batch(self):
        return self.db.execute("SELECT * FROM upload_batches WHERE repo=? AND status='pending' ORDER BY rowid LIMIT 1", (self.repo,)).fetchone()

    def prepare_batch(self, jobs):
        batch_id = uuid.uuid4().hex
        ids = [row['id'] for row in jobs]
        remote = f'data/train/{self.session_id}-{batch_id}.parquet'
        with self.db:
            self.db.execute('INSERT INTO upload_batches(id,repo,job_ids,remote_path) VALUES(?,?,?,?)',
                            (batch_id, self.repo, json.dumps(ids), remote))
            self.db.executemany('INSERT INTO upload_items VALUES(?,?,?)', [(self.repo, i, batch_id) for i in ids])
        return self.next_batch()

    def records(self, batch):
        records = []
        for job_id in json.loads(batch['job_ids']):
            job = self.db.execute("SELECT * FROM jobs WHERE id=? AND state='done'", (job_id,)).fetchone()
            if job is None:
                raise ValueError(f'Upload job no longer complete: {job_id}')
            image, prompt = self.session.paths(job)
            records.append({'id': f'{self.session_id}/{job["stem"]}', 'image': str(image),
                            'image_transparent': str(self.session.transparent_path(job)), 'prompt': str(prompt),
                            'parameters': str(self.session.output / 'parameters' / f'{job["stem"]}.json')})
        return records

    async def run(self):
        first_pending = None
        self.progress(f'Uploader ready: {self.repo}')
        while True:
            self.changed.clear()
            pending, jobs = self.next_batch(), self.unassigned()
            now = time.monotonic()
            if jobs and first_pending is None:
                first_pending = now
            all_done = self.session.counts().get('done', 0) == self.session.config['generation']['samples']
            due = len(jobs) >= self.batch_size or (first_pending is not None and now-first_pending >= self.interval) or all_done or self.stopping
            if (self.stopping or not self.pipeline.paused) and (pending or (jobs and due)) and (self.stopping or now >= self.next_retry):
                batch = pending or self.prepare_batch(jobs)
                path = self.session.output / 'uploads' / f'{batch["id"]}.parquet'
                try:
                    self.status = 'uploading'
                    self.current_batch = batch['id']
                    self.batch_records = len(json.loads(batch['job_ids']))
                    self.progress(f'Preparing batch {self.current_batch[:12]} ({self.batch_records} portraits)')
                    if not path.is_file():
                        await asyncio.to_thread(make_shard, path, self.records(batch))
                    loop = asyncio.get_running_loop()
                    context_token = _reporter.set(lambda phase: loop.call_soon_threadsafe(self.progress, phase))
                    try:
                        await asyncio.to_thread(send_shard, self.repo, self.config.get('private', True), path, batch['remote_path'])
                    finally:
                        _reporter.reset(context_token)
                    with self.db:
                        self.db.execute("UPDATE upload_batches SET status='uploaded',error=NULL WHERE id=?", (batch['id'],))
                    self.error, self.status = None, 'waiting'
                    self.pipeline.notify('upload', f'Hugging Face: uploaded {len(json.loads(batch["job_ids"]))} portraits to {self.repo}')
                    try:
                        path.unlink(missing_ok=True)
                    except OSError:
                        pass  # acknowledged cache files can be removed later
                    self.current_batch, self.batch_records = None, 0
                    self.phase = 'Waiting for completed portraits'
                    first_pending = None
                    continue
                except Exception as error:
                    self.error, self.status = str(error), 'retrying'
                    self.phase = 'Upload failed; waiting to retry'
                    with self.db:
                        self.db.execute('UPDATE upload_batches SET error=? WHERE id=?', (self.error, batch['id']))
                    self.pipeline.notify('upload', f'Hugging Face upload deferred: {error}')
                    self.next_retry = time.monotonic() + self.retry_delay
                    if self.stopping:
                        break
            if self.stopping:
                break
            if self.status != 'retrying':
                self.status = 'paused' if self.pipeline.paused else 'waiting'
            try:
                await asyncio.wait_for(self.changed.wait(), timeout=1)
            except asyncio.TimeoutError:
                pass
        self.status = 'stopped'
        self.phase = 'Saved for retry on next run' if self.error else 'Uploads drained'
