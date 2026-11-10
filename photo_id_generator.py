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
FRAMING = (
    "Photorealistic centered head-and-shoulders crop, eyes looking into the camera, "
    "face fully visible, plain light-gray background, even soft lighting."
)


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
        "max_tokens": 512,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Edit the provided synthetic ID headshot description into one concise English paragraph. "
                    "Keep the exact age and every supplied visual trait. Use the required phrases verbatim. "
                    "Do not add or replace traits, change the age, beautify the subject, or add framing. "
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


def prepare_prompt(age, prompt_seed, template):
    random.seed(prompt_seed)
    data = generate_sample_data(age)
    draft = " ".join(template.render(**data).split())
    required = [
        f"{age} years old", data["gender"], data["skin"]["tone"], data["face"]["shape"],
        data["face"]["brow"], data["eyes"]["color"], data["skin"]["texture"],
        data["skin"]["aging_note"], data["clothing"]["fit"], data["clothing"]["fabric"],
        data["face"]["forehead"], data["face"]["cheeks"], data["face"]["jaw"],
        data["face"]["nose"], data["face"]["mouth"], data["face"]["ear"],
        data["eyes"]["shape"], data["eyes"]["eyelids"], data["eyes"]["spacing"],
    ]
    required.extend(f"{piece['color']} {piece['garment']}" for piece in data["clothing"]["pieces"])
    hair = data["hair"]
    if hair["style"] != "bald":
        required.extend(phrase for phrase in (hair["color"], hair["texture"], hair["style"], hair["gray_desc"]) if phrase)
    required.extend(phrase for phrase in (
        hair["baldness_note"], hair["facial_hair"], data["face"]["detail"],
        data["metadata"]["glasses"], data["metadata"]["glare"],
        data["metadata"]["hat"] or data["metadata"]["extra_headwear"],
    ) if phrase)
    return draft, required


def render_prompt(age, prompt_seed, template, llm):
    draft, required = prepare_prompt(age, prompt_seed, template)
    return f"{finalize_prompt(draft, required, llm)} {FRAMING}"


def submit_image(workflow, prompt, seed, stem, comfyui):
    graph = copy.deepcopy(workflow)
    graph["452"]["inputs"]["prompt"] = prompt
    graph["458"]["inputs"]["seed"] = seed
    graph["461"]["inputs"]["filename_prefix"] = f"photo_id/{stem}"

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
    filename = f'photo_id_{uuid.uuid4().hex}.png'
    body = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="{filename}"\r\n'
        'Content-Type: image/png\r\n\r\n'
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


def generate_image(workflow, prompt, seed, stem, comfyui):
    return wait_image(submit_image(workflow, prompt, seed, stem, comfyui), stem, comfyui)


def main():
    parser = argparse.ArgumentParser(description="Generate synthetic portraits with Qwen Image 2.1.")
    parser.add_argument("--config", type=Path, default=ROOT / "config.yaml")
    args = parser.parse_args()
    with args.config.open(encoding="utf-8") as file:
        config = yaml.safe_load(file)

    from generation_ui import GenerationApp

    GenerationApp(config, args.config.resolve().parent).run()


if __name__ == "__main__":
    main()
