import argparse
import os

import lmstudio as lms
from rich.progress import Progress


def analyze_id_photos(input_folder, output_folder):
    # model = lms.llm("google/gemma-3-12b")
    model = lms.llm("google/gemma-3-4b")

    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    # DEFINING THE SYSTEM PROMPT
    system_prompt = (
        "You are a Fictional Identity Generator. Your task is to look at an image "
        "and create a structured JSON profile. You must output ONLY raw JSON. "
        "No explanations, no markdown code blocks, and no greeting. "
        "Current year is 2026. Ensure Age and DOB match."
    )

    user_instruction = (
        "Generate a fictional person ID in this format:"
    )

    with open("res/id_data_sample.json") as f:
        user_instruction += f"\n\n{f.read()}"

    valid_extensions = ('.jpg', '.jpeg', '.png', '.webp')
    image_files = [f for f in os.listdir(input_folder) if f.lower().endswith(valid_extensions)]

    with Progress() as progress:
        task = progress.add_task("Processing", total=len(image_files))

        for filename in image_files:
            image_path = os.path.join(input_folder, filename)
            base_name = os.path.splitext(filename)[0]
            json_path = os.path.join(output_folder, f"{base_name}.json")

            if os.path.exists(json_path):
                progress.update(task, advance=1)
                continue

            try:
                image_handle = lms.prepare_image(image_path)

                # INITIALIZING CHAT WITH SYSTEM PROMPT
                chat = lms.Chat(system_prompt)
                chat.add_user_message(user_instruction, images=[image_handle])

                response = model.respond(chat)
                content = response.content.strip()

                # Safeguard to remove markdown tags if the model ignores the system prompt
                clean_json = content.replace("```json", "").replace("```", "").strip()

                with open(json_path, "w", encoding="utf-8") as f:
                    f.write(clean_json)

            except Exception as e:
                print(f"\nError processing {filename}: {e}")

            progress.update(task, advance=1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="./idPhoto/img")
    parser.add_argument("--output", default="./idPhoto/json_profiles")
    args = parser.parse_args()
    analyze_id_photos(args.input, args.output)
