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

## Age distribution

The sampler uses [U.S. Census Bureau Vintage 2025 national resident population estimates](https://www2.census.gov/programs-surveys/popest/datasets/2020-2025/national/asrh/nc-est2025-agesex-res.csv) for July 1, 2025. It uses the total across sexes (`SEX=0`) and normalizes across adults aged 18 and older. The Census 100+ category is represented by age 100 in prompts.

The sampler allocates the batch across individual ages by largest remainder and shuffles the result using the existing seed. The bands below summarize the planned ages for the default 10,000 prompts.

| Age band | Share of U.S. adults | Prompts |
| --- | ---: | ---: |
| 18–24 | 11.84% | 1,183 |
| 25–34 | 17.26% | 1,726 |
| 35–44 | 16.80% | 1,679 |
| 45–54 | 14.88% | 1,487 |
| 55–64 | 15.27% | 1,529 |
| 65–74 | 13.60% | 1,360 |
| 75–84 | 7.74% | 775 |
| 85–94 | 2.32% | 233 |
| 95+ | 0.29% | 28 |

## Publish to Hugging Face

The publisher requires Python 3.10 or later, `datasets` and `huggingface_hub`. It skips images whose matching prompt is missing, unreadable or blank. The `body` split contains the image and prompt pairs.

```bash
python publish_data_set.py --path ./dataset/idPhoto --user your_username --dataset_name your_dataset_name
```

The [hosted dataset](https://huggingface.co/datasets/lambdaWalker/ds.photo_id) has its own dataset card and license information.
