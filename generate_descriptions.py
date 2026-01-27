import argparse
import os

import lmstudio as lms
from tqdm import tqdm


def analyze_id_photos(input_folder, description_folder):
    # model = lms.llm("allenai/olmocr-2-7b")
    model = lms.llm("google/gemma-3-4b")
    # model = lms.llm("google/gemma-3-12b")

    if not os.path.exists(description_folder):
        os.makedirs(description_folder)

    prompt_instruction = (
        "Describe the following image in dense detail. be respectful and assertive.\n"
        "Start with the description and avoid meta-comments, pleasantries.\n"
        "DO NOT MENTION THE BACKGROUND\n"
        "Describe the following image in dense detail. be respectful and assertive.\n"
        "Start with the description and avoid meta-comments, pleasantries.\n"
        "DO NOT MENTION THE BACKGROUND"
    )

    valid_extensions = ('.jpg', '.jpeg', '.png', '.webp')
    image_files = [f for f in os.listdir(input_folder) if f.lower().endswith(valid_extensions)]

    print(f"Analyzing {len(image_files)} images...")
    print("Initial estimate will appear after the first image is processed.\n")

    # UPDATED: Added desc and unit for clearer ETA display
    for filename in tqdm(image_files, desc="Processing files", unit="img"):
        image_path = os.path.join(input_folder, filename)
        base_name = os.path.splitext(filename)[0]

        desc_filename = f"{base_name}.txt"
        desc_path = os.path.join(description_folder, desc_filename)
        if os.path.exists(desc_path):
            continue

        try:
            image_handle = lms.prepare_image(image_path)
            chat = lms.Chat()
            chat.add_user_message(prompt_instruction, images=[image_handle])

            # The inference step (this is what takes time)
            response = model.respond(chat)
            description = response.content.strip()

            # Save Individual Text File (Sidecar)
            with open(desc_path, "w", encoding="utf-8") as f_txt:
                f_txt.write(description)

        except Exception as e:
            # tqdm handles print interruptions better if you use tqdm.write,
            # but standard print is fine for simple errors
            print(f"\nError processing {filename}: {e}")

    print(f"\nSuccess! Metadata files generated in '{description_folder}'.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analyze ID photos with Gemma 3 via LM Studio.")
    parser.add_argument("--input", default="./dataset/idPhoto/img", help="Folder containing images.")
    parser.add_argument("--description", default="./dataset/idPhoto/description", help="Folder for results.")

    args = parser.parse_args()
    analyze_id_photos(args.input, args.description)
