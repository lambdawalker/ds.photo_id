"""Exercise the real urllib adapters against a local HTTP server."""
import json
import threading
import unittest
import tempfile
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from photo_id_generator import ROOT, finalize_prompt, generate_image, submit_background, wait_image


class HTTPTests(unittest.TestCase):
    def test_native_gemma_thinking_off_and_qwen_download(self):
        received = {}
        png = b'\x89PNG\r\n\x1a\nfixture'

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def reply(self, value):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(value if isinstance(value, bytes) else json.dumps(value).encode())

            def do_POST(self):
                raw = self.rfile.read(int(self.headers['Content-Length']))
                if self.path == '/upload/image':
                    received['upload'] = raw
                    self.reply({'name': 'uploaded.png', 'subfolder': 'batch', 'type': 'input'})
                    return
                data = json.loads(raw)
                received[self.path] = data
                if self.path == '/api/v1/chat':
                    self.reply({'output': [{'type': 'message', 'content': json.loads(data['input'])['draft']}]})
                else:
                    self.reply({'prompt_id': 'remote-id'})

            def do_GET(self):
                if self.path.startswith('/view?'):
                    self.reply(png)
                else:
                    self.reply({'remote-id': {'status': {'status_str': 'success'}, 'outputs': {
                        '461': {'images': [{'filename': 'one.png', 'subfolder': 'photo_id', 'type': 'output'}]},
                        '6': {'images': [{'filename': 'transparent.png', 'subfolder': 'photo_id', 'type': 'output'}]}
                    }}})

        with ThreadingHTTPServer(('127.0.0.1', 0), Handler) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base = f'http://127.0.0.1:{server.server_port}'
                llm = {'enabled': True, 'url': base + '/v1', 'api': 'lmstudio', 'model': 'google/gemma-4-12b-qat', 'timeout_seconds': 2}
                prompt = finalize_prompt('A person, 20 years old.', ['20 years old'], llm)
                self.assertEqual(received['/api/v1/chat']['reasoning'], 'off')
                workflow = json.loads((ROOT / 'res/qwen_image_2_1_api.json').read_text())
                result = generate_image(workflow, prompt, 123, 'photoId_00001', {'url': base, 'timeout_seconds': 2})
                self.assertEqual(result, png)
                graph = received['/prompt']['prompt']
                self.assertEqual(graph['452']['inputs']['prompt'], prompt)
                self.assertIn('waist-up shot', graph['452']['inputs']['negative_prompt'])
                self.assertEqual(graph['458']['inputs']['seed'], 123)
                self.assertEqual(graph['461']['inputs']['filename_prefix'], 'photo_id/photoId_00001')
                self.assertNotEqual(workflow['452']['inputs']['prompt'], prompt)
                background = json.loads((ROOT / 'res/birefnet_api.json').read_text())
                with tempfile.TemporaryDirectory() as directory:
                    original = Path(directory) / 'photoId_00001.png'
                    original.write_bytes(png)
                    remote = submit_background(background, original, {'url': base})
                    self.assertEqual(wait_image(remote, original.stem, {'url': base, 'timeout_seconds': 2}, '6'), png)
                graph = received['/prompt']['prompt']
                self.assertIn(png, received['upload'])
                self.assertEqual(graph['1']['inputs']['image'], 'batch/uploaded.png')
                self.assertEqual(graph['3']['class_type'], 'RemoveBackground')
                self.assertEqual(graph['4']['class_type'], 'InvertMask')
                self.assertEqual(graph['5']['inputs']['alpha'], ['4', 0])
                self.assertEqual(graph['6']['inputs']['images'], ['5', 0])
            finally:
                server.shutdown()
                thread.join()
