"""Authenticated cleanup requests; credentials stay in environment variables."""
import json
import os
from urllib.request import Request, urlopen


def token(config):
    return os.environ.get(config.get('token_env', 'PHOTO_ID_CLEANUP_TOKEN'))


def cleanup(url, prompt_id, config):
    secret = token(config)
    if not secret:
        raise RuntimeError('Set the configured cleanup token environment variable on both machines')
    request = Request(url.rstrip('/') + '/photo-id/cleanup',
                      data=json.dumps({'prompt_ids': [prompt_id]}).encode(),
                      headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {secret}'})
    with urlopen(request, timeout=30) as response:
        result = json.load(response)
    if not result.get('ok'):
        raise RuntimeError('ComfyUI cleanup did not acknowledge success')
