"""Local browser companion; all session access stays on the pipeline event loop."""
import asyncio
from collections import deque
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import threading
from urllib.parse import urlsplit

from photo_id_generator import ROOT


class Dashboard:
    def __init__(self, session, pipeline, config):
        self.session, self.pipeline = session, pipeline
        self.config = config
        self.logs = {stage: deque(maxlen=2000) for stage in ('llm', 'image', 'upload')}
        self.loop = asyncio.get_running_loop()
        self.original_times = {}
        self.server = None
        self.thread = None
        self.sequence = 0

    def record(self, stage, message):
        self.sequence += 1
        self.logs[stage].append({'id': self.sequence, 'time': datetime.now().strftime('%H:%M:%S'), 'message': message})

    async def snapshot(self):
        s, p = self.session, self.pipeline
        counts = s.counts()
        total = s.config['generation']['samples']
        prompts = s.db.execute('SELECT COUNT(*) FROM jobs WHERE prompt IS NOT NULL').fetchone()[0]
        for stem in s.originals - self.original_times.keys():
            path = s.image_path('original', stem)
            if path.is_file():
                self.original_times[stem] = path.stat().st_mtime_ns
        latest = []
        for stem in sorted(self.original_times, key=lambda stem: (self.original_times[stem], stem), reverse=True)[:4]:
            job = s.db.execute('SELECT prompt,state,error FROM jobs WHERE stem=?', (stem,)).fetchone()
            if job is None:
                continue
            transparent = s.transparent_path({'stem': stem})
            latest.append({'parameters': f'/parameters/{stem}.json' if (s.output / 'parameters' / f'{stem}.json').is_file() else None, 'stem': stem, 'prompt': job['prompt'], 'state': job['state'], 'error': job['error'],
                           'original': f'/image/original/{s.image_path("original", stem).name}',
                           'transparent': f'/image/transparent/{transparent.name}' if transparent.is_file() else None})
        prompt_eta, image_eta, averages = p.estimates()
        done = counts.get('done', 0)
        status = 'stopping' if p.stopping else ('paused' if p.paused else ('complete' if done == total else 'running'))
        return {'retries': {stage: p.retry_snapshot(stage) for stage in ('llm','image')}, 'upload': p.upload_snapshot(), 'status': status, 'total': total, 'prompts': prompts, 'done': done,
                'ready': counts.get('ready', 0), 'capacity': s.capacity, 'failed': counts.get('failed', 0),
                'active': dict(p.active), 'work_remaining': dict(p.work_remaining), 'eta': {'llm': prompt_eta, 'image': image_eta}, 'averages': averages,
                'logs': {stage: list(lines) for stage, lines in self.logs.items()}, 'latest': latest}

    async def action(self, action):
        if self.pipeline.stopping:
            raise ValueError('Session is stopping')
        if action == 'pause':
            self.pipeline.pause()
        elif action == 'resume':
            self.pipeline.resume()
        elif action == 'retry':
            self.pipeline.retry()
            self.pipeline.resume()
        elif action == 'retry-upload':
            if not self.pipeline.uploader:
                raise ValueError('Uploader is not enabled')
            self.pipeline.uploader.retry()
        else:
            raise ValueError('Unknown action')
        return {'ok': True}

    def start(self):
        dashboard = self
        host = self.config.get('host', '127.0.0.1')
        port = self.config.get('port', 8765)
        html = (ROOT / 'web/dashboard.html').read_bytes()

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def respond(self, code, body, content_type='application/json'):
                if not isinstance(body, bytes):
                    body = json.dumps(body).encode()
                self.send_response(code)
                self.send_header('Content-Type', content_type)
                self.send_header('Content-Length', str(len(body)))
                self.send_header('Cache-Control', 'no-store')
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.end_headers()
                self.wfile.write(body)

            def valid_host(self):
                name = urlsplit('http://' + self.headers.get('Host', '')).hostname
                allowed = {'127.0.0.1', 'localhost', '::1'} if host in ('127.0.0.1', 'localhost', '::1') else {host}
                return name in allowed

            def do_GET(self):
                if not self.valid_host():
                    return self.respond(403, {'error': 'Invalid host'})
                path = urlsplit(self.path).path
                if path == '/':
                    return self.respond(200, html, 'text/html; charset=utf-8')
                if path == '/api/state':
                    try:
                        result = asyncio.run_coroutine_threadsafe(dashboard.snapshot(), dashboard.loop).result(timeout=15)
                        return self.respond(200, result)
                    except Exception:
                        return self.respond(503, {'error': 'Session unavailable'})
                match = re.fullmatch(r'/image/(original|transparent)/(photoId_\d{5,}\.(?:png|webp))', path)
                if match:
                    variant, filename = match.groups()
                    directory = (dashboard.session.output / variant).resolve()
                    target = (directory / filename).resolve()
                    if target.parent == directory and target.is_file():
                        return self.respond(200, target.read_bytes(), 'image/webp' if target.suffix == '.webp' else 'image/png')
                metadata = re.fullmatch(r'/parameters/(photoId_\d{5,}\.json)', path)
                if metadata:
                    directory = (dashboard.session.output / 'parameters').resolve()
                    target = (directory / metadata[1]).resolve()
                    if target.parent == directory and target.is_file():
                        return self.respond(200, target.read_bytes(), 'application/json')
                self.respond(404, {'error': 'Not found'})

            def do_POST(self):
                # A same-origin custom header prevents cross-site form submissions.
                origin = self.headers.get('Origin')
                if (not self.valid_host() or self.headers.get('X-Dashboard') != '1'
                        or (origin and origin != 'http://' + self.headers.get('Host', ''))):
                    return self.respond(403, {'error': 'Same-origin dashboard requests only'})
                match = re.fullmatch(r'/api/(pause|resume|retry|retry-upload)', self.path)
                if not match:
                    return self.respond(404, {'error': 'Unknown action'})
                try:
                    result = asyncio.run_coroutine_threadsafe(dashboard.action(match[1]), dashboard.loop).result(timeout=15)
                    self.respond(200, result)
                except Exception as error:
                    self.respond(409, {'error': str(error)})

        self.server = ThreadingHTTPServer((host, port), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return f'http://{host}:{self.server.server_port}'

    async def close(self):
        if self.server:
            await asyncio.to_thread(self.server.shutdown)
            self.server.server_close()
            await asyncio.to_thread(self.thread.join)
            self.server = None


async def run_web(config, config_dir):
    from generation_session import Session, Pipeline
    from generation_ui import UILogHandler
    session = await asyncio.to_thread(Session, config, config_dir)
    pipeline = Pipeline(session)
    dashboard = Dashboard(session, pipeline, config.get('web', {}))
    pipeline.notify = dashboard.record
    handler = UILogHandler(dashboard)
    from photo_id_generator import LOGGER
    LOGGER.addHandler(handler)
    try:
        print('Dashboard: ' + dashboard.start(), flush=True)
        pipeline.start()
        await asyncio.Event().wait()
    finally:
        pipeline.pause()
        await pipeline.stop()
        await dashboard.close()
        LOGGER.removeHandler(handler)
        session.close()
