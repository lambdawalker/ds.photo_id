"""Durable producer/consumer queue. SQLite is owned by the asyncio event loop."""
import asyncio
import json
import random
import sqlite3
from pathlib import Path

from filelock import FileLock
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from id_data import generate_ages
from photo_id_generator import (
    ROOT, compose_prompt, ComfyGenerationError, finalize_prompt, prepare_prompt,
    submit_image, wait_image, submit_background, png_info,
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
            ''')
            columns = {row['name'] for row in self.db.execute('PRAGMA table_info(jobs)')}
            with self.db:
                for name in ('background_id', 'background_url'):
                    if name not in columns:
                        self.db.execute(f'ALTER TABLE jobs ADD COLUMN {name} TEXT')
            self._migrate_layout()
            for name in ('original', 'transparent', 'prompts'):
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
            # Refresh only unsubmitted prompts without an existing original. In-flight
            # jobs keep the exact prompt that produced their remote image.
            for job in self.db.execute("SELECT * FROM jobs WHERE prompt IS NOT NULL AND remote_id IS NULL").fetchall():
                if not self.paths(job)[0].exists():
                    self.update(job['id'], prompt=compose_prompt(job['prompt']))
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
                draft, required = prepare_prompt(age, prompt_seed, template)
                self.db.execute('INSERT INTO jobs(id,stem,image_seed,draft,required) VALUES(?,?,?,?,?)',
                                (i, f'photoId_{i:05d}', image_seed, draft, json.dumps(required)))
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
        allowed = {'prompt', 'state', 'remote_id', 'remote_url', 'background_id', 'background_url', 'error'}
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
                    result = await asyncio.to_thread(finalize_prompt, job['draft'], json.loads(job['required']), session.config['llm'])
                    prompt = compose_prompt(result)
                    session.update(job['id'], prompt=prompt, state='ready', error=None)
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
                self.active[stage] = None
                self.changed.set()

    async def _image(self, job):
        session = self.session
        image_path, prompt_path = session.paths(job)
        transparent_path = session.transparent_path(job)
        if not image_path.exists():
            comfy = dict(session.config['comfyui'])
            remote_id = job['remote_id']
            if remote_id:
                comfy['url'] = job['remote_url']
            else:
                remote_id = await asyncio.to_thread(submit_image, session.workflow, job['prompt'], job['image_seed'], job['stem'], comfy)
                session.update(job['id'], remote_id=remote_id, remote_url=comfy['url'])
            png = await asyncio.to_thread(wait_image, remote_id, job['stem'], comfy)
            png_info(png)
            self._save(prompt_path, job['prompt'].encode('utf-8'))
            self._save(image_path, png)
            self.notify('image', f'{job["stem"]}: original saved')
        if not transparent_path.exists():
            self.notify('image', f'{job["stem"]}: removing background')
            comfy = dict(session.config['comfyui'])
            remote_id = job['background_id']
            if remote_id:
                comfy['url'] = job['background_url']
            else:
                remote_id = await asyncio.to_thread(submit_background, session.background_workflow, image_path, comfy)
                session.update(job['id'], background_id=remote_id, background_url=comfy['url'])
            png = await asyncio.to_thread(wait_image, remote_id, job['stem'], comfy, '6')
            if png_info(png, require_alpha=True) != png_info(image_path.read_bytes()):
                raise ValueError('Transparent output dimensions do not match the original')
            self._save(transparent_path, png)
        session.update(job['id'], state='done', error=None)

    @staticmethod
    def _save(path, data):
        temporary = path.with_suffix(path.suffix + '.tmp')
        temporary.write_bytes(data)
        temporary.replace(path)
