# Photo ID Dataset Generator

Generate synthetic ID-style portraits using Qwen Image 2.1 in ComfyUI. Each dataset row contains two columns.

| Column | Type | Contents |
| --- | --- | --- |
| `image` | Image | The generated portrait. |
| `prompt` | String | The original generation prompt saved with that portrait. |

## Generate portraits

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and start a ComfyUI build that supports `TextEncodeQwenImage21` and `QwenImage21Cache`. The API graph in `res/qwen_image_2_1_api.json` uses the supplied workflow's Qwen UNet, text encoder and VAE. Install those exact model files on the ComfyUI server or adjust their names in the graph.

On Linux or macOS, run `./run.sh`. On Windows, run `run.bat` (or `.\run.bat` in PowerShell). Both launchers use the locked uv environment and forward generator arguments such as `--config path/to/config.yaml`.

Edit `config.yaml` to set the ComfyUI URL, the local LLM's OpenAI-compatible API base URL and model ID, and the batch size, seed, and output directory. For a smoke test, set `generation.samples` to a small number and use a separate output directory. Set `llm.enabled: false` to use the template directly.

The external LLM edits the sampled description at low temperature. The generator checks that the sampled phrases and exact age survive, falls back to the template on a failed check or request, and appends the fixed framing. The API graph bypasses the supplied editor workflow's optional in-graph prompt refiner and uses the built-in PNG saver. Seeds are repeatable for the same batch settings. Use a fresh output directory when changing the batch size, seed, workflow, or prompt settings because reruns skip existing image/prompt pairs.

The generator writes the downloaded image and the exact positive prompt sent to ComfyUI. Files are paired by stem.

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

The publisher uses the optional `publish` dependencies. It skips images whose matching prompt is missing, unreadable or blank. The `body` split contains the image and prompt pairs.

```bash
uv run --locked --extra publish python publish_data_set.py --path ./dataset/idPhoto --user your_username --dataset_name your_dataset_name
```

The [hosted dataset](https://huggingface.co/datasets/lambdaWalker/ds.photo_id) has its own dataset card and license information.
