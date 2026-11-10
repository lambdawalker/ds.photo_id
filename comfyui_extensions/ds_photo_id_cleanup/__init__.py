"""Install this directory in ComfyUI/custom_nodes; no models or new dependencies."""
import asyncio
import hmac
import os
from pathlib import Path
import re

from aiohttp import web
import folder_paths
from server import PromptServer

NODE_CLASS_MAPPINGS = {}


def owned_path(descriptor):
    """Allow only pipeline PNG/WebP outputs and its UUID-named uploaded inputs."""
    kind = descriptor.get('type', 'output')
    filename = descriptor.get('filename', '')
    subfolder = descriptor.get('subfolder', '')
    if not isinstance(filename, str) or Path(filename).name != filename or not isinstance(subfolder, str):
        raise ValueError('Invalid image descriptor')
    if kind == 'output':
        if subfolder.replace('\\', '/') != 'photo_id' and not subfolder.replace('\\', '/').startswith('photo_id/'):
            raise ValueError('Output is outside photo_id/')
        if not re.fullmatch(r'photoId_\d{5,}_(?:[0-9a-f]{32}_)?\d+_\.(png|webp)', filename):
            raise ValueError('Not a pipeline output filename')
        root = Path(folder_paths.get_output_directory()).resolve()
    elif kind == 'input':
        if subfolder or not re.fullmatch(r'photo_id_[0-9a-f]{32}\.(png|webp)', filename):
            raise ValueError('Not a pipeline upload')
        root = Path(folder_paths.get_input_directory()).resolve()
    else:
        raise ValueError('Unsupported file type')
    candidate = root / subfolder / filename
    resolved = candidate.resolve()
    if not resolved.is_relative_to(root) or candidate.is_symlink() or resolved == root:
        raise ValueError('Image path escapes storage root')
    return resolved


def collect_files(entry):
    descriptors = []
    for node in entry.get('outputs', {}).values():
        descriptors.extend(node.get('images', []))
    graph = entry.get('prompt', [None, None, {}])[2]
    for node in graph.values():
        if node.get('class_type') == 'LoadImage':
            image = node.get('inputs', {}).get('image', '')
            descriptors.append({'type': 'input', 'filename': image, 'subfolder': ''})
    # Validate the entire request before touching any file.
    return [owned_path(item) for item in descriptors]


@PromptServer.instance.routes.post('/photo-id/cleanup')
async def cleanup(request):
    secret = os.environ.get('PHOTO_ID_CLEANUP_TOKEN', '')
    if not secret or not hmac.compare_digest(request.headers.get('Authorization', ''), f'Bearer {secret}'):
        return web.json_response({'error': 'Unauthorized'}, status=401)
    try:
        data = await request.json()
        ids = data.get('prompt_ids')
        if not isinstance(ids, list) or not 1 <= len(ids) <= 16 or any(not isinstance(i, str) for i in ids):
            raise ValueError('Expected 1–16 prompt IDs')
        queue = PromptServer.instance.prompt_queue
        entries = {pid: queue.get_history(prompt_id=pid).get(pid) for pid in ids}
        if any(entry and entry.get('status', {}).get('status_str') != 'success' for entry in entries.values()):
            return web.json_response({'error': 'Job has not succeeded'}, status=409)
        paths = [path for entry in entries.values() if entry for path in collect_files(entry)]
        # History that was lost cannot tell us which files were owned; leave it pending.
        if any(entry is None for entry in entries.values()):
            return web.json_response({'error': 'Job history unavailable; files left untouched'}, status=409)
        for path in paths:
            await asyncio.to_thread(path.unlink, missing_ok=True)
        # Retain history so retrying after a lost acknowledgement is idempotent.
        return web.json_response({'ok': True, 'deleted_files': len(paths)})
    except (ValueError, TypeError, KeyError, IndexError) as error:
        return web.json_response({'error': str(error)}, status=400)
