"""Dataset image encoding; ComfyUI transport remains PNG."""
from io import BytesIO
from PIL import Image


def settings(config):
    result = {'format': config.get('format', 'png'), 'quality': config.get('quality', 90),
              'lossless': config.get('lossless', False), 'method': 6}
    if result['format'] not in ('png', 'webp'):
        raise ValueError('generation.image_storage.format must be png or webp')
    if not isinstance(result['quality'], int) or not 0 <= result['quality'] <= 100:
        raise ValueError('WebP quality must be an integer between 0 and 100')
    return result


def encode(png, options):
    if options['format'] == 'png':
        return png
    with Image.open(BytesIO(png)) as image:
        output = BytesIO()
        image.save(output, format='WEBP', quality=options['quality'], lossless=options['lossless'],
                   method=options['method'], exact=True)
        return output.getvalue()


def info(data, require_alpha=False):
    with Image.open(BytesIO(data)) as image:
        image.load()
        if image.format not in ('PNG', 'WEBP'):
            raise ValueError('Expected a PNG or WebP image')
        if require_alpha and 'A' not in image.getbands():
            raise ValueError('Transparent output must have an alpha channel')
        return image.size
