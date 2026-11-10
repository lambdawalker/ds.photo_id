"""Textual dashboard for the persistent photo generation pipeline."""
import asyncio
import logging
import time

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Footer, Header, ProgressBar, RichLog, Static

from generation_session import Pipeline, Session
from photo_id_generator import LOGGER
from processing_estimates import duration


class UILogHandler(logging.Handler):
    def __init__(self, app):
        super().__init__(logging.WARNING)
        self.app = app
        self.loop = asyncio.get_running_loop()

    def emit(self, record):
        self.loop.call_soon_threadsafe(self.app.record, 'llm', record.getMessage())


class GenerationApp(App):
    TITLE = 'Portrait Studio'
    SUB_TITLE = 'Qwen Image · persistent generation queue'
    CSS = '''
    Screen { background: #101820; color: #dce6ed; }
    Header { background: #1b2b38; height: 1; }
    #summary { height: 1; padding: 0 1; color: #6de2ca; }
    #location { display: none; height: 1; padding: 0 1; color: #9baebc; }
    #panels { height: 1fr; overflow-y: auto; }
    .panel { width: 1fr; margin: 0; border: round #39556a; padding: 0 1; }
    .heading { height: 1; text-style: bold; color: #6de2ca; }
    .endpoint { display: none; height: 1; color: #9baebc; }
    .metrics { height: 2; }
    .timing { height: 1; color: #9baebc; }
    .current { height: 1; color: #e8c884; }
    ProgressBar { width: 1fr; height: 1; }
    ProgressBar > Bar { width: 1fr; }
    RichLog { height: 1fr; min-height: 3; background: #14212b; border-top: solid #39556a; }
    #controls { height: 3; align-horizontal: center; padding: 0; }
    Button { margin: 0 1; }
    Footer { background: #1b2b38; }
    .compact #panels { layout: vertical; }
    .compact .panel { width: 1fr; height: 1fr; min-height: 11; }
    .details #location, .details .endpoint { display: block; }
    '''
    BINDINGS = [
        ('space', 'toggle_pause', 'Pause / resume'),
        ('d', 'toggle_details', 'Connection details'),
        ('r', 'retry', 'Retry failures'),
        ('shift+r', 'resubmit', 'Resubmit lost jobs'),
        ('q', 'save_exit', 'Save & exit'),
        ('ctrl+c', 'save_exit', 'Save & exit'),
    ]

    def __init__(self, config, config_dir):
        super().__init__()
        self.config = config
        self.config_dir = config_dir
        self.session = None
        self.pipeline = None
        self.closing = False
        self.handler = None
        self.init_task = None
        self.eta_cache = None
        self.eta_updated = 0
        self.dashboard = None

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static('Preparing saved session…', id='summary', markup=False)
        yield Static(str(self.config_dir / self.config['generation']['output_dir']), id='location', markup=False)
        with Horizontal(id='panels'):
            for stage, title, endpoint in (
                ('llm', '01  PROMPT GENERATION', self.config['llm']['url'] if self.config['llm']['enabled'] else 'Template mode · LLM disabled'),
                ('image', '02  IMAGE GENERATION', self.config['comfyui']['url']),
            ):
                with Vertical(classes='panel'):
                    yield Static(title, classes='heading')
                    yield Static(endpoint, classes='endpoint', markup=False)
                    yield Static('Preparing…', id=f'{stage}-metrics', classes='metrics', markup=False)
                    yield ProgressBar(total=self.config['generation']['samples'], show_eta=False, id=f'{stage}-progress')
                    yield Static('Waiting', id=f'{stage}-current', classes='current', markup=False)
                    yield Static('ETA: measuring…', id=f'{stage}-timing', classes='timing', markup=False)
                    yield RichLog(id=f'{stage}-log', wrap=True, min_width=1, max_lines=2000, markup=False)
        with Horizontal(id='controls'):
            yield Button('Pause', id='pause', variant='warning', disabled=True)
            yield Button('Retry failures', id='retry', disabled=True)
            yield Button('Save & exit', id='exit', variant='primary')
        yield Footer()

    async def on_mount(self):
        # Sample/snapshot the batch without freezing the UI during initialization.
        self.init_task = asyncio.create_task(asyncio.to_thread(Session, self.config, self.config_dir))
        try:
            self.session = await self.init_task
        except Exception as error:
            self.query_one('#summary', Static).update(f'Cannot open session: {error}')
            return
        self.handler = UILogHandler(self)
        LOGGER.addHandler(self.handler)
        self.pipeline = Pipeline(self.session, self.record)
        if self.config.get('web', {}).get('enabled', False):
            from web_dashboard import Dashboard
            self.dashboard = Dashboard(self.session, self.pipeline, self.config['web'])
            try:
                url = self.dashboard.start()
                self.sub_title = url
                self.record('image', f'Web dashboard: {url}')
            except OSError as error:
                self.dashboard = None
                self.record('image', f'Web dashboard could not start: {error}')
        self.pipeline.start()
        self.query_one('#pause', Button).disabled = False
        self.query_one('#retry', Button).disabled = False
        self.record('llm', 'Session loaded. Saved prompts and seeds are reused.')
        self.record('image', 'Originals are retained; missing transparent images are generated.')
        for job in self.session.db.execute("SELECT stem,prompt,error FROM jobs WHERE state='failed' LIMIT 20"):
            self.record('llm' if job['prompt'] is None else 'image', f'{job["stem"]}: {job["error"]}')
        self.set_interval(0.2, self.refresh_progress)
        self.refresh_progress()

    def on_resize(self, event):
        self.screen.set_class(event.size.width < 100, 'compact')

    def record(self, stage, message):
        if self.dashboard:
            self.dashboard.record(stage, message)
        self.query_one(f'#{stage}-log', RichLog).write(message)

    def refresh_progress(self):
        if not self.pipeline:
            return
        counts = self.session.counts()
        total = self.config['generation']['samples']
        prompts = self.session.db.execute('SELECT COUNT(*) FROM jobs WHERE prompt IS NOT NULL').fetchone()[0]
        done, ready, failed = (counts.get(key, 0) for key in ('done', 'ready', 'failed'))
        llm_failed = self.session.db.execute("SELECT COUNT(*) FROM jobs WHERE state='failed' AND prompt IS NULL").fetchone()[0]
        active = any(self.pipeline.active.values())
        if self.closing:
            status = 'Saving — waiting for active requests to finish…'
        elif self.pipeline.paused:
            status = 'Pausing — finishing active requests…' if active else 'Paused — safe to exit and resume later'
        elif done == total:
            status = 'Complete — originals, transparent images and prompts saved'
        else:
            status = 'Running — prompt and image workers operate concurrently'
        self.query_one('#summary', Static).update(status)
        self.query_one('#llm-metrics', Static).update(f'{prompts:,} / {total:,} prompts prepared\nReady queue: {ready:,} / {self.session.capacity:,} · Failures: {llm_failed:,}')
        self.query_one('#image-metrics', Static).update(f'{done:,} / {total:,} portraits complete (both images)\nFailures: {failed - llm_failed:,} · In flight: {int(bool(self.pipeline.active["image"]))}')
        self.query_one('#llm-progress', ProgressBar).update(progress=prompts)
        self.query_one('#image-progress', ProgressBar).update(progress=done)
        for stage in ('llm', 'image'):
            current = self.pipeline.active[stage]
            idle = 'Paused' if self.pipeline.paused else ('Complete' if (prompts if stage == 'llm' else done) == total else ('Waiting for queue space' if stage == 'llm' and ready >= self.session.capacity else 'Waiting for work'))
            self.query_one(f'#{stage}-current', Static).update(f'Working: {current}' if current else idle)
        if self.eta_cache is None or time.monotonic() - self.eta_updated >= 1:
            self.eta_cache = self.pipeline.estimates()
            self.eta_updated = time.monotonic()
        prompt_eta, image_eta, averages = self.eta_cache
        for stage, eta, average in (
            ('llm', prompt_eta, averages.get('llm')),
            ('image', image_eta, (averages['original'] + averages['background'])
             if 'original' in averages and 'background' in averages else None),
        ):
            label = 'On resume' if self.pipeline.paused else 'ETA'
            complete = (prompts if stage == 'llm' else done) == total
            value = 'complete' if complete else ('measuring…' if eta is None else f'~{duration(eta)}')
            speed = '' if average is None else f' · avg {duration(average)}/'+('prompt' if stage == 'llm' else 'portrait')
            self.query_one(f'#{stage}-timing', Static).update(f'{label}: {value}{speed}')
        self.query_one('#pause', Button).label = 'Resume' if self.pipeline.paused else 'Pause'
        self.query_one('#retry', Button).disabled = failed == 0 or self.closing

    def action_toggle_details(self):
        self.screen.toggle_class('details')

    def action_toggle_pause(self):
        if self.pipeline and not self.closing:
            self.pipeline.resume() if self.pipeline.paused else self.pipeline.pause()
            self.refresh_progress()

    def action_retry(self):
        if self.pipeline and not self.closing:
            self.pipeline.retry()
            self.pipeline.resume()
            self.record('image', 'Failed jobs requeued; saved prompts are retained.')
            self.refresh_progress()

    def action_resubmit(self):
        if self.pipeline and not self.closing:
            self.pipeline.retry(resubmit=True)
            self.pipeline.resume()
            self.record('image', 'Failed jobs will be submitted again with their saved prompts and seeds.')
            self.refresh_progress()

    async def action_save_exit(self):
        if self.closing:
            return
        self.closing = True
        self.query_one('#pause', Button).disabled = True
        self.query_one('#retry', Button).disabled = True
        if self.init_task and not self.init_task.done():
            self.query_one('#summary', Static).update('Finishing session initialization before exit…')
            try:
                await self.init_task
            except Exception:
                pass
        if self.pipeline:
            self.refresh_progress()
            await self.pipeline.stop()
        self.exit()

    async def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == 'pause':
            self.action_toggle_pause()
        elif event.button.id == 'retry':
            self.action_retry()
        elif event.button.id == 'exit':
            await self.action_save_exit()

    async def on_unmount(self):
        # Also drain workers if Textual exits through another route.
        if self.pipeline:
            await self.pipeline.stop()
        if self.handler:
            LOGGER.removeHandler(self.handler)
        if self.dashboard:
            await self.dashboard.close()
        if self.session:
            self.session.close()
