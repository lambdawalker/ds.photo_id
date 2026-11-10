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
    ROOT, FRAMING, ComfyGenerationError, finalize_prompt, prepare_prompt,
    submit_image, wait_image,
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
            for name in ('img', 'prompt'):
                (self.output / name).mkdir(exist_ok=True)
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

    def _reconcile_files(self):
        for job in self.db.execute('SELECT * FROM jobs').fetchall():
            image, prompt = self.paths(job)
            if image.exists():
                if not prompt.is_file():
                    raise ValueError(f'Existing image has no prompt: {image}')
                text = prompt.read_text(encoding='utf-8')
                with image.open('rb') as stream:
                    valid = stream.read(8) == b'\x89PNG\r\n\x1a\n'
                if not text.strip() or not valid or (job['prompt'] and job['prompt'] != text):
                    raise ValueError(f'Existing image/prompt pair is inconsistent: {job["stem"]}')
                if job['state'] != 'done':
                    self.update(job['id'], state='done', prompt=text, error=None)
            elif job['state'] == 'done':
                self.update(job['id'], state='ready', remote_id=None, remote_url=None)

    def paths(self, job):
        return self.output / 'img' / f'{job["stem"]}.png', self.output / 'prompt' / f'{job["stem"]}.txt'

    def update(self, job_id, **values):
        allowed = {'prompt', 'state', 'remote_id', 'remote_url', 'error'}
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
                self.db.execute("UPDATE jobs SET remote_id=NULL, remote_url=NULL WHERE state='failed'")
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
                    prompt = f'{result} {FRAMING}'
                    session.update(job['id'], prompt=prompt, state='ready', error=None)
                    self.notify(stage, f'{job["stem"]} → ready queue')
                else:
                    await self._image(job)
                    self.notify(stage, f'{job["stem"]} saved')
            except Exception as error:
                values = {'state': 'failed', 'error': str(error)}
                if isinstance(error, ComfyGenerationError):
                    values.update(remote_id=None, remote_url=None)
                session.update(job['id'], **values)
                self.notify(stage, f'{job["stem"]}: {error}')
                # Stop dispatching after a service failure instead of failing the entire batch.
                self.paused = True
            finally:
                self.active[stage] = None
                self.changed.set()

    async def _image(self, job):
        session = self.session
        comfy = dict(session.config['comfyui'])
        remote_id = job['remote_id']
        if remote_id:
            # Poll the server that accepted this job even if the config URL changed.
            comfy['url'] = job['remote_url']
        else:
            remote_id = await asyncio.to_thread(submit_image, session.workflow, job['prompt'], job['image_seed'], job['stem'], comfy)
            session.update(job['id'], remote_id=remote_id, remote_url=comfy['url'])
        png = await asyncio.to_thread(wait_image, remote_id, job['stem'], comfy)
        image_path, prompt_path = session.paths(job)
        # Commit prompt before image; a crash before DB update is reconciled on open.
        prompt_temp = prompt_path.with_suffix('.txt.tmp')
        image_temp = image_path.with_suffix('.png.tmp')
        prompt_temp.write_text(job['prompt'], encoding='utf-8')
        image_temp.write_bytes(png)
        prompt_temp.replace(prompt_path)
        image_temp.replace(image_path)
        session.update(job['id'], state='done', error=None)
