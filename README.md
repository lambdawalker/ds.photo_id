# Photo ID Dataset Generator

Generate synthetic ID-style portraits using Flux 1 in ComfyUI. Each dataset row contains two columns.

| Column | Type | Contents |
| --- | --- | --- |
| `image` | Image | The generated portrait. |
| `prompt` | String | The original generation prompt saved with that portrait. |

## Generate portraits

Start ComfyUI with Flux 1 at `http://127.0.0.1:8188/` and run the generator from the repository root.

```bash
python photo_id_generator.py
```

Place the generated images and prompt files in the layout below. Pair files by their filename stem.

```text
dataset/idPhoto/
├── img/
│   └── photoId_00001.png
└── prompt/
    └── photoId_00001.txt
```

## Publish to Hugging Face

The publisher requires Python 3.10 or later, `datasets` and `huggingface_hub`. It skips images whose matching prompt is missing, unreadable or blank. The `body` split contains the image and prompt pairs.

```bash
python publish_data_set.py --path ./dataset/idPhoto --user your_username --dataset_name your_dataset_name
```

The [hosted dataset](https://huggingface.co/datasets/lambdaWalker/ds.photo_id) has its own dataset card and license information.
