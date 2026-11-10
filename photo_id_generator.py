import argparse
import copy
import json
import logging
import random
import re
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from id_data import generate_ages, generate_sample_data

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


def render_prompt(age, prompt_seed, template, llm):
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
    return f"{finalize_prompt(draft, required, llm)} {FRAMING}"


def generate_image(workflow, prompt, seed, stem, comfyui):
    graph = copy.deepcopy(workflow)
    graph["452"]["inputs"]["prompt"] = prompt
    graph["458"]["inputs"]["seed"] = seed
    graph["461"]["inputs"]["filename_prefix"] = f"photo_id/{stem}"

    url = comfyui["url"].rstrip("/")
    deadline = time.monotonic() + comfyui["timeout_seconds"]
    queued = request_json(f"{url}/prompt", 30, {"prompt": graph})
    prompt_id = queued.get("prompt_id")
    if not prompt_id:
        raise RuntimeError(f"ComfyUI rejected the workflow: {queued}")

    while time.monotonic() < deadline:
        history = request_json(f"{url}/history/{prompt_id}", 30).get(prompt_id)
        if history:
            status = history.get("status", {})
            if status.get("status_str") == "error":
                raise RuntimeError(f"ComfyUI generation failed for {stem}: {status.get('messages')}")
            images = history.get("outputs", {}).get("461", {}).get("images", [])
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


def main():
    parser = argparse.ArgumentParser(description="Generate synthetic portraits with Qwen Image 2.1.")
    parser.add_argument("--config", type=Path, default=ROOT / "config.yaml")
    args = parser.parse_args()
    with args.config.open(encoding="utf-8") as file:
        config = yaml.safe_load(file)

    generation = config["generation"]
    output = args.config.resolve().parent / generation["output_dir"]
    image_dir, prompt_dir = output / "img", output / "prompt"
    for directory in (image_dir, prompt_dir):
        directory.mkdir(parents=True, exist_ok=True)

    env = Environment(loader=FileSystemLoader(ROOT / "res"), undefined=StrictUndefined)
    template = env.get_template("photoId.j2")
    workflow = json.loads((ROOT / "res/qwen_image_2_1_api.json").read_text(encoding="utf-8"))
    seed = generation["seed"]
    ages = generate_ages(generation["samples"], seed=seed)
    sample_seeds = random.Random(seed)

    for index, age in enumerate(ages, start=1):
        prompt_seed = sample_seeds.getrandbits(64)
        image_seed = sample_seeds.getrandbits(53)
        stem = f"photoId_{index:05d}"
        image_path, prompt_path = image_dir / f"{stem}.png", prompt_dir / f"{stem}.txt"
        if image_path.is_file():
            if not prompt_path.is_file():
                raise RuntimeError(f"Existing image has no saved prompt: {image_path}")
            continue

        LOGGER.info("Generating %s (%d/%d)", stem, index, len(ages))
        prompt = render_prompt(age, prompt_seed, template, config["llm"])
        png = generate_image(workflow, prompt, image_seed, stem, config["comfyui"])
        temporary_image = image_path.with_suffix(".png.tmp")
        temporary_image.write_bytes(png)
        prompt_path.write_text(prompt, encoding="utf-8")
        temporary_image.replace(image_path)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
