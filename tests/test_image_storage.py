from io import BytesIO
import unittest
from PIL import Image
from image_storage import encode, info, settings


class ImageStorageTests(unittest.TestCase):
    def test_lossy_webp_preserves_alpha_and_dimensions(self):
        image = Image.new('RGBA', (32, 32), (120, 90, 50, 0))
        for x in range(32):
            for y in range(32):
                image.putpixel((x,y), (x*7,y*7,100,x*8))
        buffer = BytesIO()
        image.save(buffer, format='PNG')
        encoded = encode(buffer.getvalue(), settings({'format': 'webp', 'quality': 90}))
        self.assertTrue(encoded.startswith(b'RIFF'))
        self.assertEqual(info(encoded, True), (32,32))
        with Image.open(BytesIO(encoded)) as decoded:
            self.assertEqual(decoded.getchannel('A').tobytes(), image.getchannel('A').tobytes())


class WebPPipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_pipeline_saves_webp_and_metadata_paths(self):
        import copy,json,tempfile
        from pathlib import Path
        from unittest.mock import patch
        from generation_session import Session,Pipeline
        from test_generation import CONFIG,PNG,until
        with tempfile.TemporaryDirectory() as tmp:
            config=copy.deepcopy(CONFIG);config['generation']['samples']=1
            config['generation']['image_storage']={'format':'webp','quality':90}
            session=Session(config,Path(tmp));pipeline=Pipeline(session)
            with patch('generation_session.submit_image',return_value='original'),patch('generation_session.submit_background',return_value='background'),patch('generation_session.wait_image',return_value=PNG):
                pipeline.start()
                await until(lambda: session.counts().get('done')==1)
                await pipeline.stop()
            metadata=json.loads((session.output/'parameters/photoId_00001.json').read_text())
            for variant in ('original','transparent'):
                self.assertTrue(metadata['files'][variant].endswith('.webp'))
                self.assertEqual(info((session.output/metadata['files'][variant]).read_bytes(),variant=='transparent'),(1,1))
            session.close()
            session=Session(config,Path(tmp))
            self.assertEqual(session.counts()['done'],1)
            session.close()
