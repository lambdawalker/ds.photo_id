import argparse
import logging
import os

from datasets import Dataset, Features, Image, Value, DatasetDict
from huggingface_hub import HfApi

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def compile_photo_id_dataset(data_path: str) -> Dataset:
    """Pair each image with its original generation prompt."""
    features = Features({"image": Image(), "prompt": Value("string")})
    img_dir = os.path.join(data_path, "img")
    prompt_dir = os.path.join(data_path, "prompt")

    for directory in (img_dir, prompt_dir):
        if not os.path.isdir(directory):
            raise FileNotFoundError(f"Required directory not found: {directory}")

    def data_generator():
        for filename in sorted(os.listdir(img_dir)):
            img_path = os.path.join(img_dir, filename)
            if not os.path.isfile(img_path) or not filename.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                continue

            stem = os.path.splitext(filename)[0]
            prompt_path = os.path.join(prompt_dir, f"{stem}.txt")
            try:
                with open(prompt_path, encoding="utf-8", newline="") as prompt_file:
                    prompt = prompt_file.read()
            except (OSError, UnicodeError) as exc:
                logger.warning("Skipping %s: cannot read generation prompt (%s)", filename, exc)
                continue

            if not prompt.strip():
                logger.warning("Skipping %s: generation prompt is empty", filename)
                continue

            yield {"image": img_path, "prompt": prompt}

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
            path_in_repo="dataset/idPhoto/README.md",
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
    parser.add_argument("--path", type=str, default="./dataset/idPhoto", help="Path to the root data directory containing img and prompt folders.")
    parser.add_argument("--user", type=str, default="lambdaWalker", help="Hugging Face username or organization.")
    parser.add_argument("--dataset_name", type=str, default="ds.photo_id", help="Name of the dataset repository.")

    # Readme arguments
    parser.add_argument("--readme_path", type=str, default="./dataset/idPhoto/README.md", help="Path to a local README.md file to upload.")

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
