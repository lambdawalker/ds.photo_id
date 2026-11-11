import argparse
import copy
import json
import logging
import random
import re
import time
import uuid
import struct
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import yaml

from id_data import generate_sample_data

ROOT = Path(__file__).resolve().parent
LOGGER = logging.getLogger(__name__)
LEGACY_FRAMING = (
    "Photorealistic centered head-and-shoulders crop, eyes looking into the camera, "
    "face fully visible, plain light-gray background, even soft lighting."
)


FRAMING = (
    "Photorealistic tight passport-style headshot, straight-on camera at eye level. "
    "The centered head is the dominant subject: crown to chin occupies about two thirds "
    "of the image height, with a small clear margin above the hair or headwear. "
    "Keep the entire head and chin inside the frame. Show the neck and upper shoulders "
    "at the bottom edge; the shoulders extend beyond the left and right edges. "
    "Only the neckline and uppermost part of the clothing are visible. "
    "Head generally facing the camera with only subtle pose variation, face fully visible, "
    "plain light-gray background, even soft lighting."
)
NEGATIVE_PROMPT = (
    "3d render, illustration, full body, mid-body shot, waist-up shot, half-length portrait, "
    "fashion editorial, wide shot, distant subject, small head, visible waist, visible hands, "
    "cropped crown, cropped chin"
)


def compose_prompt(description):
    """Put fixed composition first, outside the LLM's editable description."""
    description = description.strip()
    if description.startswith(FRAMING):
        return description
    if description.endswith(LEGACY_FRAMING):
        description = description[:-len(LEGACY_FRAMING)].strip()
    return f"{FRAMING} Subject details within this tight crop: {description}"


def request_bytes(url, timeout, payload=None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(url, data=data, headers={"Content-Type": "application/json"} if data else {})
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.read()
    except HTTPError as error:
        detail = error.read(2048).decode("utf-8", errors="replace")
        raise RuntimeError(f"{url} returned HTTP {error.code}: {detail}") from error


def request_json(url, timeout, payload=None):
    return json.loads(request_bytes(url, timeout, payload))


def finalize_prompt(draft, required_phrases, llm):
    if not llm["enabled"]:
        return draft

    payload = {
        "model": llm["model"],
        "temperature": 0.1,
        "max_tokens": 1024,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Edit the provided synthetic ID headshot description into one concise English paragraph. "
                    "Keep the exact age and every supplied visual trait. Use the required phrases verbatim. "
                    "Do not add or replace traits, change the age, beautify the subject, or add framing. "
                    "Describe clothing only as visible at the neckline and upper shoulders. "
                    "Never introduce a wider view to display an outfit, scarf, or jacket. "
                    "Return only the edited portrait description."
                ),
            },
            {
                "role": "user",
                "content": json.dumps({"draft": draft, "required_phrases": required_phrases}),
            },
        ],
    }
    try:
        if llm.get("api", "openai") == "lmstudio":
            native_payload = {
                "model": payload["model"],
                "system_prompt": payload["messages"][0]["content"],
                "input": payload["messages"][1]["content"],
                "temperature": payload["temperature"],
                "max_output_tokens": payload["max_tokens"],
                "reasoning": "off",
                "store": False,
            }
            base_url = llm["url"].rstrip("/").removesuffix("/v1")
            response = request_json(
                f"{base_url}/api/v1/chat", llm["timeout_seconds"], native_payload
            )
            candidate = " ".join(
                item["content"] for item in response["output"] if item["type"] == "message"
            ).strip()
        else:
            payload["chat_template_kwargs"] = {"enable_thinking": False}
            response = request_json(
                f"{llm['url'].rstrip('/')}/chat/completions", llm["timeout_seconds"], payload
            )
            candidate = response["choices"][0]["message"]["content"].strip()
        normalized = " ".join(candidate.casefold().split())
        if not candidate or len(candidate.split()) > 260 or "\n" in candidate or "<think>" in normalized:
            raise ValueError("expected one short portrait paragraph")
        if any(phrase.casefold() not in normalized for phrase in required_phrases):
            raise ValueError("rewrite omitted a required trait")
        if re.findall(r"\b\d+\b", normalized) != re.findall(r"\b\d+\b", draft):
            raise ValueError("rewrite changed a numeric value")
        return candidate
    except (URLError, TimeoutError, RuntimeError, ValueError, KeyError, IndexError, TypeError, AttributeError) as error:
        LOGGER.warning("Using template prompt after LLM rewrite failed: %s", error)
        return draft


def prepare_prompt(age, prompt_seed, template, include_data=False):
    random.seed(prompt_seed)
    data = generate_sample_data(age)
    draft = " ".join(template.render(**data).split())
    required = [
        f"{age} years old", data["gender"], data["skin"]["tone"], data["face"]["shape"],
        data["face"]["brow"], data["skin"]["texture"],
        data["skin"]["aging_note"], data["clothing"]["fit"], data["clothing"]["fabric"],
        data["face"]["forehead"], data["face"]["cheeks"], data["face"]["jaw"],
        data["face"]["nose"], data["face"]["mouth"], data["face"]["ear"],
        data["eyes"]["shape"], data["eyes"]["eyelids"], data["eyes"]["spacing"],
    ]
    required.extend(phrase for phrase in (
        data["metadata"]["expression"], data["build"]["description"],
        data["skin"]["birthmark"]["description"], data["eyes"]["vision"]["description"],
    ) if phrase)
    if data["eyes"]["vision"]["eye_appearance"] != "opaque":
        required.append(data["eyes"]["color"])
    required.extend(f"{piece['color']} {piece['garment']}" for piece in data["clothing"]["pieces"])
    hair = data["hair"]
    if hair["style"] != "bald":
        required.extend(phrase for phrase in (hair["color"], hair["texture"], hair["style"], hair["gray_desc"]) if phrase)
    required.extend(phrase for phrase in (
        hair["baldness_note"], hair["facial_hair"], hair["stray_hair"], data["face"]["detail"],
        data["metadata"]["glasses"], data["metadata"]["glare"],
        data["metadata"]["hat"], data["metadata"]["extra_headwear"],
        data["clothing"]["condition"],
    ) if phrase)
    required.extend(data["metadata"][key] for key in (
        "lens", "lighting", "quality_profile", "motion_hint", "head_tilt", "head_yaw",
        "shoulders", "grooming", "makeup", "jewelry", "body_detail",
    ) if data["metadata"][key])
    return (draft, required, data) if include_data else (draft, required)


def build_image_graph(workflow, prompt, seed, stem):
    graph = copy.deepcopy(workflow)
    graph["452"]["inputs"]["prompt"] = prompt
    graph["452"]["inputs"]["negative_prompt"] = NEGATIVE_PROMPT
    graph["458"]["inputs"]["seed"] = seed
    graph["461"]["inputs"]["filename_prefix"] = f"photo_id/{stem}_{uuid.uuid4().hex}"

    return graph


def submit_image(workflow, prompt, seed, stem, comfyui, graph=None):
    graph = graph if graph is not None else build_image_graph(workflow, prompt, seed, stem)
    url = comfyui["url"].rstrip("/")
    queued = request_json(f"{url}/prompt", 30, {"prompt": graph})
    prompt_id = queued.get("prompt_id")
    if not prompt_id:
        raise RuntimeError(f"ComfyUI rejected the workflow: {queued}")

    return prompt_id


class ComfyGenerationError(RuntimeError):
    """A server-reported terminal failure; retry needs a new submission."""


def wait_image(prompt_id, stem, comfyui, output_node="461"):
    url = comfyui["url"].rstrip("/")
    deadline = time.monotonic() + comfyui["timeout_seconds"]
    while time.monotonic() < deadline:
        history = request_json(f"{url}/history/{prompt_id}", 30).get(prompt_id)
        if history:
            status = history.get("status", {})
            if status.get("status_str") == "error":
                raise ComfyGenerationError(f"ComfyUI generation failed for {stem}: {status.get('messages')}")
            images = history.get("outputs", {}).get(output_node, {}).get("images", [])
            if len(images) != 1:
                raise RuntimeError(f"Expected one ComfyUI output for {stem}, got {len(images)}")
            image = images[0]
            query = urlencode({key: image[key] for key in ("filename", "subfolder", "type")})
            png = request_bytes(f"{url}/view?{query}", 30)
            if not png.startswith(b"\x89PNG\r\n\x1a\n"):
                raise RuntimeError(f"ComfyUI did not return a PNG for {stem}")
            return png
        time.sleep(1)

    raise TimeoutError(f"ComfyUI did not finish {stem} within the configured timeout")


def png_info(data, require_alpha=False):
    if len(data) < 33 or not data.startswith(b"\x89PNG\r\n\x1a\n") or data[12:16] != b'IHDR':
        raise ValueError('Expected a PNG with a valid IHDR header')
    size = struct.unpack('>II', data[16:24])
    if not all(size) or (require_alpha and data[25] != 6):
        raise ValueError('Transparent output must be an RGBA PNG')
    return size


def submit_background(workflow, image_path, comfyui):
    """Upload the saved original, then run the native BiRefNet graph."""
    boundary = uuid.uuid4().hex
    extension = image_path.suffix.lower()
    filename = f'photo_id_{uuid.uuid4().hex}{extension}'
    mime = 'image/webp' if extension == '.webp' else 'image/png'
    body = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="{filename}"\r\n'
        f'Content-Type: {mime}\r\n\r\n'
    ).encode() + image_path.read_bytes() + f'\r\n--{boundary}--\r\n'.encode()
    url = comfyui['url'].rstrip('/')
    request = Request(f'{url}/upload/image', data=body,
                      headers={'Content-Type': f'multipart/form-data; boundary={boundary}'})
    with urlopen(request, timeout=30) as response:
        uploaded = json.load(response)
    name = uploaded['name']
    if uploaded.get('subfolder'):
        name = f"{uploaded['subfolder']}/{name}"
    graph = copy.deepcopy(workflow)
    graph['1']['inputs']['image'] = name
    graph['6']['inputs']['filename_prefix'] = f'photo_id/transparent/{image_path.stem}'
    queued = request_json(f'{url}/prompt', 30, {'prompt': graph})
    if not queued.get('prompt_id'):
        raise RuntimeError(f'ComfyUI rejected background removal: {queued}')
    return queued['prompt_id']


def main():
    parser = argparse.ArgumentParser(description="Generate synthetic portraits with Qwen Image 2.1.")
    parser.add_argument("--config", type=Path, default=ROOT / "config.yaml")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--order-hf-shards", action="store_true", help="Order previously uploaded shards using the saved session journal")
    modes.add_argument("--reset-data", action="store_true", help="Delete configured local and HF portrait data and squash HF main history; stop generation first")
    modes.add_argument("--web", action="store_true", help="Run the browser dashboard without the terminal UI")
    args = parser.parse_args()
    with args.config.open(encoding="utf-8") as file:
        config = yaml.safe_load(file)

    if args.reset_data:
        from reset_dataset import reset_dataset
        reset_dataset(config, args.config.resolve().parent)
    elif args.order_hf_shards:
        from generation_session import Session, Pipeline
        from incremental_upload import LiveUploader, order_uploaded_batches
        session = Session(config, args.config.resolve().parent)
        try:
            uploader = LiveUploader(Pipeline(session))
            count = order_uploaded_batches(uploader)
            print(f'Finished: {count} shard names ordered. No images were regenerated.')
        finally:
            session.close()
    elif args.web:
        import asyncio
        from web_dashboard import run_web
        try:
            asyncio.run(run_web(config, args.config.resolve().parent))
        except KeyboardInterrupt:
            pass
    else:
        from generation_ui import GenerationApp
        GenerationApp(config, args.config.resolve().parent).run()


if __name__ == "__main__":
    main()
