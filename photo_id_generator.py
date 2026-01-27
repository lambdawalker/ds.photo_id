import os
import random

from comfy_api_simplified import ComfyApiWrapper, ComfyWorkflowWrapper
from jinja2 import Environment, FileSystemLoader
from rich.progress import Progress

from id_data import generate_sample_data, generate_ages

OUTPUT_DIR = "output"
PREFIX = "photoId"


def load_template_environment():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return Environment(loader=FileSystemLoader(base_dir))


def render_prompt(age, template_env):
    template = template_env.get_template('photoId.j2')
    sample_data = generate_sample_data(age)
    rendered_prompt = template.render(**sample_data)
    return rendered_prompt


def configure_workflow(wf, prompt, steps=15):
    wf.set_node_param("prompt", "text", prompt)
    wf.set_node_param("output", "filename_prefix", f"{OUTPUT_DIR}/{PREFIX}")
    wf.set_node_param("output", "prompt_data", prompt)
    wf.set_node_param("KSampler", "steps", steps)
    wf.set_node_param("KSampler", "seed", random.randint(0, 99999999999))


def get_prompt_file_path(image_data):
    return f"prompt/{image_data.split('.')[0]}.txt"


def output_exists(index):
    prompt_file_path = f"output/person_{(index + 1):05d}_.txt"
    return os.path.exists(prompt_file_path)


def process_sample(index, age):
    try:
        if output_exists(index):
            return index, True, "skipped"

        api = ComfyApiWrapper("http://127.0.0.1:8188/")
        wf = ComfyWorkflowWrapper("flux1_api.json")
        template_env = load_template_environment()

        prompt = render_prompt(age, template_env)
        configure_workflow(wf, prompt)

        results = api.queue_and_wait_images(wf, "output")
    except Exception as e:
        return index, False, str(e)


def main():
    samples = 10000

    ages = generate_ages(samples, seed=42)
    with Progress() as progress:
        task = progress.add_task("Processing", total=samples)

        for i in range(samples):
            if output_exists(i):
                print(f"Skipping sample {i} as output already exists.")
                continue

            process_sample(i, ages[i])
            progress.update(task, advance=1)


if __name__ == "__main__":
    main()
