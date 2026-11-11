import asyncio
import copy
import json
from pathlib import Path
import tempfile
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from generation_session import Pipeline, Session
from web_dashboard import Dashboard
from test_generation import CONFIG, PNG


class DashboardTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.session = Session(copy.deepcopy(CONFIG), Path(self.temp.name))
        self.pipeline = Pipeline(self.session)
        self.dashboard = Dashboard(self.session, self.pipeline, {'port': 0})
        self.url = self.dashboard.start()

    async def asyncTearDown(self):
        await self.dashboard.close()
        self.session.close()
        self.temp.cleanup()

    async def request(self, path, action=False, headers=None):
        def get():
            request = Request(self.url + path, method='POST' if action else 'GET', headers=headers or {})
            with urlopen(request, timeout=3) as response:
                return response.read(), response.headers['Content-Type']
        return await asyncio.to_thread(get)

    async def test_latest_four_and_pending_transparency(self):
        for i in range(1, 6):
            self.session.update(i, prompt=f'Exact prompt {i}', state='ready')
            job = self.session.db.execute('SELECT * FROM jobs WHERE id=?', (i,)).fetchone()
            self.session.paths(job)[0].write_bytes(PNG)
            self.session.originals.add(job['stem'])
            if i == 5:
                self.session.transparent_path(job).write_bytes(PNG)
        self.session.write_parameters(5)
        self.dashboard.record('llm', '<script>untrusted prompt</script>')
        body, _ = await self.request('/api/state')
        state = json.loads(body)
        self.assertEqual(set(state['work_remaining']), {'llm', 'image'})
        self.assertIn('upload',state['logs'])
        self.assertEqual(len(state['latest']), 4)
        self.assertEqual(state['latest'][0]['stem'], 'photoId_00005')
        self.assertIsNotNone(state['latest'][0]['transparent'])
        self.assertIsNone(state['latest'][1]['transparent'])
        self.assertEqual(state['latest'][0]['prompt'], 'Exact prompt 5')
        metadata, _ = await self.request(state['latest'][0]['parameters'])
        self.assertIn('age', json.loads(metadata))
        metadata, _ = await self.request(state['latest'][0]['metadata'])
        self.assertEqual(json.loads(metadata)['id'], 'photoId_00005')
        draft, kind = await self.request(state['latest'][0]['draft_prompt'])
        self.assertTrue(draft)
        self.assertTrue(kind.startswith('text/plain'))
        image, kind = await self.request(state['latest'][0]['transparent'])
        self.assertEqual((image, kind), (PNG, 'image/png'))
        self.assertEqual(state['logs']['llm'][0]['message'], '<script>untrusted prompt</script>')

    async def test_controls_share_pipeline_and_require_header(self):
        await self.request('/api/pause', True, {'X-Dashboard': '1'})
        self.assertTrue(self.pipeline.paused)
        await self.request('/api/resume', True, {'X-Dashboard': '1'})
        self.assertFalse(self.pipeline.paused)
        with self.assertRaises(HTTPError) as error:
            await self.request('/api/pause', True)
        self.assertEqual(error.exception.code, 403)
        with self.assertRaises(HTTPError):
            await self.request('/api/pause', True, {'X-Dashboard': '1', 'Origin': 'https://other.example'})
        self.assertFalse(self.pipeline.paused)

    async def test_only_image_routes_are_served(self):
        body, kind = await self.request('/')
        self.assertIn(b'Latest 4 generations', body)
        self.assertTrue(kind.startswith('text/html'))
        for path in ('/image/original/../../config.yaml', '/config.yaml', '/image/prompts/photoId_00001.txt'):
            with self.assertRaises(HTTPError) as error:
                await self.request(path)
            self.assertEqual(error.exception.code, 404)

    async def test_terminal_companion_shares_controls_and_closes_server(self):
        from unittest.mock import patch
        from generation_ui import GenerationApp
        config = copy.deepcopy(CONFIG)
        config['generation']['output_dir'] = 'terminal-session'
        config['web'] = {'enabled': True, 'host': '127.0.0.1', 'port': 0}
        with patch('generation_session.submit_image', side_effect=RuntimeError('test server offline')):
            app = GenerationApp(config, Path(self.temp.name))
            async with app.run_test(size=(120, 35)) as pilot:
                await pilot.pause()
                self.assertIsNotNone(app.dashboard)
                self.assertIs(app.dashboard.pipeline, app.pipeline)
                await app.dashboard.action('pause')
                self.assertTrue(app.pipeline.paused)
                state = await app.dashboard.snapshot()
                self.assertTrue(state['logs']['image'])
                await app.action_save_exit()
            self.assertIsNone(app.dashboard.server)
