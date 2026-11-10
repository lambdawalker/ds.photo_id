"""Durable producer/consumer queue. SQLite is owned by the asyncio event loop."""
import asyncio
import json
import random
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

from filelock import FileLock
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from id_data import generate_ages
from processing_estimates import estimate, rolling_averages
from photo_id_generator import (
    ROOT, compose_prompt, ComfyGenerationError, finalize_prompt, prepare_prompt,
    submit_image, wait_image, submit_background, png_info, build_image_graph,
)


class Session:
    def __init__(self, config, config_dir):
        self.config = config
        generation = config['generation']
        self.capacity = generation.get('prompt_queue_size', 64)
        if not isinstance(self.capacity, int) or self.capacity < 1:
            raise ValueError('generation.prompt_queue_size must be a positive integer')
        if not isinstance(generation['samples'], int) or generation['samples'] < 1:
            raise ValueError('generation.samples must be a positive integer')
        self.output = (Path(config_dir) / generation['output_dir']).resolve()
        self.output.mkdir(parents=True, exist_ok=True)
        self.lock = FileLock(self.output / 'session.lock', timeout=0, thread_local=False)
        self.lock.acquire()
        try:
            self.db = sqlite3.connect(self.output / 'session.sqlite3', check_same_thread=False)
            self.db.row_factory = sqlite3.Row
            self.db.execute('PRAGMA journal_mode=WAL')
            self.db.execute('PRAGMA synchronous=FULL')
            self.db.executescript('''
                CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS jobs (
                    id INTEGER PRIMARY KEY, stem TEXT UNIQUE NOT NULL,
                    image_seed INTEGER NOT NULL, draft TEXT NOT NULL, required TEXT NOT NULL,
                    prompt TEXT, state TEXT NOT NULL DEFAULT 'pending',
                    remote_id TEXT, remote_url TEXT, error TEXT
                );
                CREATE INDEX IF NOT EXISTS jobs_state ON jobs(state, id);
                CREATE TABLE IF NOT EXISTS timings (
                    id INTEGER PRIMARY KEY, stage TEXT NOT NULL, seconds REAL NOT NULL
                );
            ''')
            columns = {row['name'] for row in self.db.execute('PRAGMA table_info(jobs)')}
            with self.db:
                for name in ('background_id', 'background_url', 'parameters'):
                    if name not in columns:
                        self.db.execute(f'ALTER TABLE jobs ADD COLUMN {name} TEXT')
            self._migrate_layout()
            for name in ('original', 'transparent', 'prompts', 'parameters'):
                (self.output / name).mkdir(parents=True, exist_ok=True)
            with self.db:
                self.db.execute('INSERT OR IGNORE INTO meta VALUES(?,?)',
                                ('background_workflow', (ROOT / 'res/birefnet_api.json').read_text(encoding='utf-8')))
            self.background_workflow = json.loads(self.db.execute(
                "SELECT value FROM meta WHERE key='background_workflow'").fetchone()['value'])
            settings = {'samples': generation['samples'], 'seed': generation['seed']}
            saved = self.db.execute("SELECT value FROM meta WHERE key='settings'").fetchone()
            if saved:
                if json.loads(saved['value']) != settings:
                    raise ValueError('Batch size/seed differ from the saved session. Use its original settings or a new output_dir.')
            else:
                self._initialize(settings)
            self.workflow = json.loads(self.db.execute("SELECT value FROM meta WHERE key='workflow'").fetchone()['value'])
            # An interrupted HTTP call may be retried; saved remote IDs avoid re-submission.
            with self.db:
                self.db.execute("UPDATE jobs SET state='pending' WHERE state='prompting'")
                self.db.execute("UPDATE jobs SET state='ready' WHERE state='rendering'")
            self._reconcile_files()
            self.originals = {path.stem for path in (self.output / "original").glob("*.png")}
            # Refresh only unsubmitted prompts without an existing original. In-flight
            # jobs keep the exact prompt that produced their remote image.
            for job in self.db.execute("SELECT * FROM jobs WHERE prompt IS NOT NULL AND remote_id IS NULL").fetchall():
                if not self.paths(job)[0].exists():
                    self.update(job['id'], prompt=compose_prompt(job['prompt']))
            for job in self.db.execute('SELECT id,stem FROM jobs').fetchall():
                if job['stem'] in self.originals:
                    self.write_parameters(job['id'])
        except BaseException:
            self.close()
            raise

    def _initialize(self, settings):
        template = Environment(loader=FileSystemLoader(ROOT / 'res'), undefined=StrictUndefined).get_template('photoId.j2')
        workflow = (ROOT / 'res/qwen_image_2_1_api.json').read_text(encoding='utf-8')
        rng = random.Random(settings['seed'])
        with self.db:
            for i, age in enumerate(generate_ages(settings['samples'], seed=settings['seed']), 1):
                prompt_seed, image_seed = rng.getrandbits(64), rng.getrandbits(53)
                draft, required, sample = prepare_prompt(age, prompt_seed, template, include_data=True)
                metadata = {'sample': sample, 'prompt_seed': prompt_seed, 'batch': settings,
                            'provenance': 'captured_at_sampling'}
                if (self.output / 'original' / f'photoId_{i:05d}.png').is_file():
                    # Importing files without a journal cannot establish their old inputs.
                    draft, required = '', []
                    metadata = {'sample': None, 'prompt_seed': None, 'batch': None,
                                'image_seed_unknown': True, 'provenance': 'legacy_partial',
                                'missing_history': 'Images imported without their generation journal; original traits, seeds and execution settings are unknown.'}
                self.db.execute('INSERT INTO jobs(id,stem,image_seed,draft,required,parameters) VALUES(?,?,?,?,?,?)',
                                (i, f'photoId_{i:05d}', image_seed, draft, json.dumps(required), json.dumps(metadata)))
            self.db.executemany('INSERT INTO meta VALUES(?,?)', [
                ('settings', json.dumps(settings)), ('workflow', workflow),
            ])

    def _migrate_layout(self):
        # Restartable moves: never overwrite a different existing file.
        for old, new in (('img', 'original'), ('images/original', 'original'),
                         ('images/transparent', 'transparent'), ('prompt', 'prompts')):
            source, target = self.output / old, self.output / new
            if not source.exists():
                continue
            target.mkdir(parents=True, exist_ok=True)
            for item in source.iterdir():
                destination = target / item.name
                if destination.exists():
                    if not item.is_file() or item.read_bytes() != destination.read_bytes():
                        raise ValueError(f'Folder migration conflict: {destination}')
                    item.unlink()
                else:
                    item.rename(destination)
            source.rmdir()
        images = self.output / 'images'
        if images.is_dir() and not any(images.iterdir()):
            images.rmdir()

    def _reconcile_files(self):
        for job in self.db.execute('SELECT * FROM jobs').fetchall():
            image, prompt = self.paths(job)
            transparent = self.transparent_path(job)
            if transparent.exists() and not image.exists():
                raise ValueError(f'Transparent image has no original: {transparent}')
            if image.exists():
                if not prompt.is_file():
                    raise ValueError(f'Existing image has no prompt: {image}')
                text = prompt.read_text(encoding='utf-8')
                size = png_info(image.read_bytes())
                if not text.strip() or (job['prompt'] and job['prompt'] != text):
                    raise ValueError(f'Existing image/prompt pair is inconsistent: {job["stem"]}')
                complete = transparent.is_file()
                if complete and png_info(transparent.read_bytes(), require_alpha=True) != size:
                    raise ValueError(f'Image dimensions differ: {job["stem"]}')
                state = 'done' if complete else ('failed' if job['state'] == 'failed' else 'ready')
                self.update(job['id'], state=state, prompt=text,
                            error=None if complete else job['error'])
            elif job['state'] == 'done':
                self.update(job['id'], state='ready', remote_id=None, remote_url=None,
                            background_id=None, background_url=None)

    def paths(self, job):
        return self.output / 'original' / f'{job["stem"]}.png', self.output / 'prompts' / f'{job["stem"]}.txt'

    def transparent_path(self, job):
        return self.output / 'transparent' / f'{job["stem"]}.png'

    def update(self, job_id, **values):
        allowed = {'prompt', 'state', 'remote_id', 'remote_url', 'background_id', 'background_url', 'error', 'parameters'}
        if not values or not values.keys() <= allowed:
            raise ValueError('Invalid job update')
        with self.db:
            self.db.execute(f'UPDATE jobs SET {", ".join(key+"=?" for key in values)} WHERE id=?',
                            (*values.values(), job_id))

    def next(self, state):
        return self.db.execute('SELECT * FROM jobs WHERE state=? ORDER BY id LIMIT 1', (state,)).fetchone()

    def counts(self):
        return dict(self.db.execute('SELECT state,COUNT(*) FROM jobs GROUP BY state').fetchall())

    def retry(self, resubmit=False):
        with self.db:
            if resubmit:
                self.db.execute("UPDATE jobs SET remote_id=NULL, remote_url=NULL, background_id=NULL, background_url=NULL WHERE state='failed'")
            self.db.execute("UPDATE jobs SET state=CASE WHEN prompt IS NULL THEN 'pending' ELSE 'ready' END, error=NULL WHERE state='failed'")

    def capture_parameters(self, job_id, **values):
        row = self.db.execute('SELECT parameters FROM jobs WHERE id=?', (job_id,)).fetchone()
        metadata = json.loads(row['parameters']) if row['parameters'] else {
            'sample': None, 'prompt_seed': None, 'batch': None,
            'provenance': 'legacy_partial',
            'missing_history': 'Structured traits, prompt seed and execution settings were not saved by the older generator.'}
        metadata.update(values)
        self.update(job_id, parameters=json.dumps(metadata))
        self.write_parameters(job_id)

    def write_parameters(self, job_id):
        job = self.db.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone()
        metadata = json.loads(job['parameters']) if job['parameters'] else {
            'sample': None, 'prompt_seed': None, 'batch': None,
            'provenance': 'legacy_partial',
            'missing_history': 'Structured traits, prompt seed and execution settings were not saved by the older generator.'}
        record = {**metadata, 'schema_version': 1, 'id': job['stem'],
                  'image_seed': None if metadata.get('image_seed_unknown') else job['image_seed'], 'draft_prompt': job['draft'],
                  'required_phrases': json.loads(job['required']), 'prompt': job['prompt'],
                  'files': {'original': f'original/{job["stem"]}.png',
                            'transparent': f'transparent/{job["stem"]}.png',
                            'prompt': f'prompts/{job["stem"]}.txt'}}
        path = self.output / 'parameters' / f'{job["stem"]}.json'
        temporary = path.with_suffix('.json.tmp')
        temporary.write_text(json.dumps(record, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        temporary.replace(path)

    def record_time(self, stage, seconds):
        with self.db:
            self.db.execute('INSERT INTO timings(stage, seconds) VALUES(?,?)', (stage, seconds))
            self.db.execute('DELETE FROM timings WHERE stage=? AND id NOT IN '
                            '(SELECT id FROM timings WHERE stage=? ORDER BY id DESC LIMIT 30)', (stage, stage))

    def averages(self):
        return rolling_averages(self.db.execute('SELECT stage, seconds FROM timings'))

    def close(self):
        if hasattr(self, 'db'):
            self.db.close()
        self.lock.release()


class Pipeline:
    """One LLM worker and one Comfy worker; blocking I/O runs in separate threads."""
    def __init__(self, session, notify=lambda stage, message: None):
        self.session = session
        self.notify = notify
        self.paused = False
        self.stopping = False
        self.active = {'llm': None, 'image': None}
        self.changed = asyncio.Event()
        self.tasks = []
        self.running = {}

    async def timed(self, stage, function, *args, learn=True):
        self.running[stage] = time.monotonic()
        try:
            result = await asyncio.to_thread(function, *args)
            if learn:
                self.session.record_time(stage, time.monotonic() - self.running[stage])
            return result
        finally:
            self.running.pop(stage, None)

    def estimates(self):
        rows = self.session.db.execute('SELECT stem, prompt, state FROM jobs').fetchall()
        remaining = [row for row in rows if row['state'] != 'done']
        pending = sum(row['prompt'] is None for row in remaining)
        missing = sum(row['stem'] not in self.session.originals for row in remaining)
        elapsed = {key: time.monotonic() - start for key, start in self.running.items()}
        averages = self.session.averages()
        prompt_eta, image_eta = estimate(pending, len(remaining), missing, self.session.capacity,
                                         averages, elapsed, any(row['prompt'] is not None for row in remaining))
        return prompt_eta, image_eta, averages

    def start(self):
        self.tasks = [asyncio.create_task(self._worker('llm')), asyncio.create_task(self._worker('image'))]

    def pause(self):
        self.paused = True
        self.changed.set()

    def resume(self):
        self.paused = False
        self.changed.set()

    def retry(self, resubmit=False):
        self.session.retry(resubmit=resubmit)
        self.changed.set()

    async def stop(self):
        self.stopping = True
        self.changed.set()
        await asyncio.gather(*self.tasks)

    async def _worker(self, stage):
        session = self.session
        while not self.stopping:
            # No awaits between clearing, checking and claiming: no lost wakeups.
            self.changed.clear()
            counts = session.counts()
            full = counts.get('ready', 0) >= session.capacity
            job = None if self.paused or (stage == 'llm' and full) else session.next('pending' if stage == 'llm' else 'ready')
            if job is None:
                await self.changed.wait()
                continue
            session.update(job['id'], state='prompting' if stage == 'llm' else 'rendering')
            self.active[stage] = job['stem']
            self.notify(stage, f'Starting {job["stem"]}')
            try:
                if stage == 'llm':
                    result = await self.timed('llm', finalize_prompt, job['draft'], json.loads(job['required']), session.config['llm'])
                    prompt = compose_prompt(result)
                    session.update(job['id'], prompt=prompt, state='ready', error=None)
                    session.capture_parameters(job['id'], prompt_finalization={
                        'enabled': session.config['llm']['enabled'],
                        'model': session.config['llm'].get('model'),
                        'api': session.config['llm'].get('api', 'openai'),
                        'temperature': 0.1, 'thinking': False,
                        'result': 'template' if result == job['draft'] else 'rewritten'})
                    self.notify(stage, f'{job["stem"]} → ready queue')
                else:
                    await self._image(job)
                    self.notify(stage, f'{job["stem"]} saved')
            except Exception as error:
                values = {'state': 'failed', 'error': str(error)}
                if isinstance(error, ComfyGenerationError):
                    values.update(remote_id=None, remote_url=None, background_id=None, background_url=None)
                session.update(job['id'], **values)
                self.notify(stage, f'{job["stem"]}: {error}')
                # Stop dispatching after a service failure instead of failing the entire batch.
                self.paused = True
            finally:
                if stage == 'image':
                    self.running.pop('original', None)
                    self.running.pop('background', None)
                self.active[stage] = None
                self.changed.set()

    async def _image(self, job):
        session = self.session
        image_path, prompt_path = session.paths(job)
        transparent_path = session.transparent_path(job)
        if not image_path.exists():
            comfy = dict(session.config['comfyui'])
            phase_start = time.monotonic()
            self.running['original'] = phase_start
            remote_id = job['remote_id']
            if remote_id:
                comfy['url'] = job['remote_url']
            else:
                session.capture_parameters(job['id'], image_seed_unknown=False, image_requested_at=datetime.now(timezone.utc).isoformat(), image_workflow=build_image_graph(
                    session.workflow, job['prompt'], job['image_seed'], job['stem']))
                remote_id = await asyncio.to_thread(submit_image, session.workflow, job['prompt'], job['image_seed'], job['stem'], comfy)
                session.update(job['id'], remote_id=remote_id, remote_url=comfy['url'])
            png = await asyncio.to_thread(wait_image, remote_id, job['stem'], comfy)
            png_info(png)
            self._save(prompt_path, job['prompt'].encode('utf-8'))
            self._save(image_path, png)
            session.originals.add(job['stem'])
            if not job['remote_id']:
                session.record_time('original', time.monotonic() - phase_start)
            self.running.pop('original', None)
            self.notify('image', f'{job["stem"]}: original saved')
        if not transparent_path.exists():
            self.notify('image', f'{job["stem"]}: removing background')
            comfy = dict(session.config['comfyui'])
            phase_start = time.monotonic()
            self.running['background'] = phase_start
            remote_id = job['background_id']
            if remote_id:
                comfy['url'] = job['background_url']
            else:
                session.capture_parameters(job['id'], background_removal={
                    'workflow': session.background_workflow,
                    'source': f'original/{job["stem"]}.png'})
                remote_id = await asyncio.to_thread(submit_background, session.background_workflow, image_path, comfy)
                session.update(job['id'], background_id=remote_id, background_url=comfy['url'])
            png = await asyncio.to_thread(wait_image, remote_id, job['stem'], comfy, '6')
            if png_info(png, require_alpha=True) != png_info(image_path.read_bytes()):
                raise ValueError('Transparent output dimensions do not match the original')
            self._save(transparent_path, png)
            if not job['background_id']:
                session.record_time('background', time.monotonic() - phase_start)
            self.running.pop('background', None)
        session.update(job['id'], state='done', error=None)

    @staticmethod
    def _save(path, data):
        temporary = path.with_suffix(path.suffix + '.tmp')
        temporary.write_bytes(data)
        temporary.replace(path)
