# Photo ID Dataset Generator

This repository contains a suite of tools designed to generate a high-quality, synthetic Photo ID dataset. It leverages AI models for image generation (Flux 1 via ComfyUI) and metadata generation (Gemma 3 via LM Studio) to create realistic ID-style headshots paired with dense natural language descriptions and structured JSON identity profiles.

## Overview

The project automates the entire pipeline of dataset creation:
1.  **Image Generation**: Uses Flux 1 to generate consistent, high-quality professional headshots.
2.  **Visual Description**: Employs Gemma 3 4B to generate "respectful and assertive" dense descriptions of each image.
3.  **Identity Synthesis**: Uses Gemma 3 4B to create detailed fictional personal data (names, DOB, addresses, physical traits) matching the generated images.
4.  **Dataset Compilation**: Packages the images and metadata into a Hugging Face compatible format and uploads it to the Hub.

## Project Structure

```text
.
├── res/                    # Resources (workflows, templates, schemas)
│   ├── flux1_api.json      # ComfyUI workflow for Flux 1
│   ├── photoId.j2          # Jinja2 template for prompts
│   └── id_data_sample.json # Sample schema for JSON profiles
├── photo_id_generator.py   # Script to generate images via ComfyUI
├── generate_descriptions.py # Script to generate text descriptions via LM Studio
├── generate_id_data.py     # Script to generate JSON profiles via LM Studio
├── validate_id_data_schema.py # Validation tool for generated JSON
└── publish_data_set.py     # Compiler and uploader for Hugging Face
```

## Prerequisites

- **ComfyUI**: Required for image generation. Must be running with the Flux 1 model available.
- **LM Studio**: Required for description and JSON profile generation. Recommended model: `google/gemma-3-4b`.
- **Python 3.10+**: With required dependencies (see scripts for specific imports like `datasets`, `huggingface_hub`, `rich`, `jinja2`).

## Usage

### 1. Generate Images
Ensure ComfyUI is running at `http://127.0.0.1:8188/`.
```bash
python photo_id_generator.py
```
This will generate images based on the templates in `res/` and save them to the `output` directory (which you should then move to `dataset/idPhoto/img`).

### 2. Generate Descriptions
Ensure LM Studio is running a local server with Gemma 3.
```bash
python generate_descriptions.py --input ./dataset/idPhoto/img --description ./dataset/idPhoto/description
```

### 3. Generate Identity Profiles (JSON)
```bash
python generate_id_data.py --input ./dataset/idPhoto/img --output ./dataset/idPhoto/json_profiles
```

### 4. Validate Profiles
```bash
python validate_id_data_schema.py --path ./dataset/idPhoto/json_profiles
```

### 5. Publish to Hugging Face
```bash
python publish_data_set.py --path ./dataset/idPhoto --user your_username --dataset_name your_dataset_name
```

## Dataset Details

For detailed information about the dataset structure, schema, and license, please refer to https://huggingface.co/datasets/lambdaWalker/ds.photo_id

## License

This project code is provided as-is. The generated dataset is typically licensed under CC-BY-4.0 (check the dataset sub-README for specifics).
