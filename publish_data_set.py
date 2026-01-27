import argparse
import json
import logging
import os

from datasets import Dataset, Features, Image, Value, DatasetDict
from huggingface_hub import HfApi

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def compile_photo_id_dataset(data_path: str) -> Dataset:
    """
    Generates a Hugging Face Dataset from a local directory structure.
    Now includes structured JSON metadata for the person's identity.
    """
    # Define the structured features for the JSON metadata
    # This matches the schema we designed earlier
    features = Features({
        "image": Image(),
        "prompt": Value("string"),
        "description": Value("string"),
        "file_id": Value("string"),
        "card": {
            "identification": {
                "first_name": Value("string"),
                "last_name": Value("string"),
                "date_of_birth": Value("string"),
                "age": Value("int32"),
                "gender": Value("string"),
                "ethnicity": Value("string")
            },
            "contact_info": {
                "address": {
                    "street": Value("string"),
                    "city": Value("string"),
                    "state_province": Value("string"),
                    "postal_code": Value("string"),
                    "country": Value("string")
                },
                "email": Value("string"),
                "phone_number": Value("string")
            },
            "biometric_details": {
                "eye_color": Value("string"),
                "height_cm": Value("int32"),
                "weight_kg": Value("int32"),
                "blood_type": Value("string")
            },
            "metadata": {
                "occupation": Value("string"),
                "citizen_status": Value("string"),
                "issue_date": Value("string")
            }
        }
    })

    img_dir = os.path.join(data_path, "img")
    prompt_dir = os.path.join(data_path, "prompt")
    desc_dir = os.path.join(data_path, "description")
    json_dir = os.path.join(data_path, "json_profiles")  # Added new folder path

    # Validate directories exist
    required_dirs = [img_dir, prompt_dir, desc_dir, json_dir]
    if not all(os.path.exists(d) for d in required_dirs):
        raise FileNotFoundError(f"Missing one or more required subdirectories in '{data_path}'")

    def data_generator():
        filenames = sorted([f for f in os.listdir(img_dir) if f.lower().endswith((".png", ".jpg", ".jpeg"))])

        if not filenames:
            logger.warning(f"No images found in {img_dir}")
            return

        for filename in filenames:
            file_id = os.path.splitext(filename)[0]

            img_path = os.path.join(img_dir, filename)
            prompt_path = os.path.join(prompt_dir, f"{file_id}.txt")
            desc_path = os.path.join(desc_dir, f"{file_id}.txt")
            json_path = os.path.join(json_dir, f"{file_id}.json")  # Added JSON file path

            # Check if all companion files exist
            if all(os.path.exists(p) for p in [prompt_path, desc_path, json_path]):
                try:
                    with open(prompt_path, "r", encoding="utf-8") as f:
                        prompt_text = f.read().strip()
                    with open(desc_path, "r", encoding="utf-8") as f:
                        desc_text = f.read().strip()
                    with open(json_path, "r", encoding="utf-8") as f:
                        profile_data = json.load(f)
                        profile_info = profile_data

                    yield {
                        "image": img_path,
                        "prompt": prompt_text,
                        "description": desc_text,
                        "file_id": file_id,
                        "card": profile_info
                    }
                except Exception as e:
                    logger.error(f"Error processing {file_id}: {e}")
            else:
                logger.debug(f"Skipping {file_id}: Missing one or more metadata files.")

    return Dataset.from_generator(data_generator, features=features)


def upload_readme(repo_id: str, readme_path: str, token: str = None):
    """
    Uploads a local README.md file to the Hugging Face Hub repository.
    """
    if not os.path.exists(readme_path):
        logger.error(f"README file not found at: {readme_path}")
        return

    logger.info(f"Uploading README from {readme_path} to {repo_id}...")
    api = HfApi(token=token)

    try:
        api.upload_file(
            path_or_fileobj=readme_path,
            path_in_repo="README.md",
            repo_id=repo_id,
            repo_type="dataset",
            commit_message="Update Dataset Card (README)"
        )
        logger.info("README uploaded successfully.")
    except Exception as e:
        logger.error(f"Failed to upload README: {e}")


def main():
    parser = argparse.ArgumentParser(description="Compile and upload a Photo ID dataset to Hugging Face.")

    # Dataset arguments
    parser.add_argument("--path", type=str, default="../raw_data", help="Path to the root data directory containing img, prompt, and description folders.")
    parser.add_argument("--user", type=str, default="lambdaWalker", help="Hugging Face username or organization.")
    parser.add_argument("--dataset_name", type=str, default="ds.photo_id", help="Name of the dataset repository.")

    # Readme arguments
    parser.add_argument("--readme_path", type=str, default="../README.md", help="Path to a local README.md file to upload.")

    # Auth/Config arguments
    parser.add_argument("--token", type=str, default=None, help="Hugging Face API token (optional if logged in via CLI).")
    parser.add_argument("--private", default=False, action="store_true", help="Set to true if the dataset repository should be private.")

    args = parser.parse_args()

    # Construct Repo ID
    repo_id = f"{args.user}/{args.dataset_name}"

    # 1. Compile and Push Dataset
    logger.info(f"Compiling dataset from '{args.path}'...")
    try:
        ds = compile_photo_id_dataset(args.path)
        dataset_dict = DatasetDict({"body": ds})

        logger.info(f"Pushing dataset to {repo_id}...")

        # Push the DatasetDict instead of the single Dataset
        dataset_dict.push_to_hub(repo_id, token=args.token, private=args.private)
        logger.info("Dataset pushed successfully.")

    except Exception as e:
        logger.error(f"Failed to compile or push dataset: {e}")
        return

    if args.readme_path:
        upload_readme(repo_id, args.readme_path, args.token)


if __name__ == "__main__":
    main()
