# Photo ID Dataset Generator

Generate synthetic ID-style portraits using Qwen Image 2.1 in ComfyUI. Each dataset row contains both image variants and their shared prompt.

| Column | Type | Contents |
| --- | --- | --- |
| `image` | Image | The original generated portrait. |
| `image_transparent` | Image | The same portrait with an RGBA transparent background. |
| `prompt` | String | The original generation prompt saved with that portrait. |

## Generate portraits

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and start a ComfyUI build that supports `TextEncodeQwenImage21` and `QwenImage21Cache`. The API graph in `res/qwen_image_2_1_api.json` uses the supplied workflow's Qwen UNet, text encoder and VAE. Install those exact model files on the ComfyUI server or adjust their names in the graph.

On Linux or macOS, run `./run.sh`. On Windows, run `run.bat` (or `.\run.bat` in PowerShell). Both launchers use the locked uv environment and forward generator arguments such as `--config path/to/config.yaml`.

Edit `config.yaml` to set the ComfyUI URL, the local LLM's OpenAI-compatible API base URL and model ID, and the batch size, seed, and output directory. For a smoke test, set `generation.samples` to a small number and use a separate output directory. Set `llm.enabled: false` to use the template directly.

The external LLM edits the sampled description at low temperature. The generator checks that the sampled phrases and exact age survive, falls back to the template on a failed check or request, and appends the fixed framing. The API graph bypasses the supplied editor workflow's optional in-graph prompt refiner and uses the built-in PNG saver. Seeds are repeatable for the same batch settings. Each output directory is a resumable session. Its sampled descriptions, required traits, image seeds, completed prompts, and workflow are saved once. Use a fresh output directory to change batch size, seed, workflow, or sampled prompt settings. Endpoint settings can be changed between runs; an already-submitted image is polled on its original server.

The generator saves the original before running BiRefNet on the ComfyUI server. It then saves a transparent RGBA PNG with matching dimensions. Both images share the exact positive prompt sent to Qwen and are matched by filename stem.

```text
dataset/idPhoto/
├── images/
│   ├── original/
│   │   └── photoId_00001.png
│   └── transparent/
│       └── photoId_00001.png
├── prompts/
│   └── photoId_00001.txt
└── session.sqlite3
```

## Background removal setup

On the **ComfyUI machine** (your DGX Spark), update ComfyUI to a build that includes `LoadBackgroundRemovalModel` and `RemoveBackground`. Download [birefnet.safetensors](https://huggingface.co/Comfy-Org/BiRefNet/resolve/main/background_removal/birefnet.safetensors) into `ComfyUI/models/background_removal/` and restart ComfyUI. No segmentation model is loaded by the Textual client.

The separate `res/birefnet_api.json` graph follows the [official native BiRefNet workflow](https://docs.comfy.org/tutorials/utility/remove-background-birefnet): load the saved original, predict the mask, invert it for `JoinImageWithAlpha`, and save RGBA PNG. It retains soft mask edges and the original dimensions. The graph is snapshotted into each session on first use. Select a different model filename in that graph before creating a new session if needed.

Original generation and background removal run sequentially in the image worker while the LLM worker continues preparing prompts. The original is committed locally before the removal workflow is submitted. Background job IDs are saved separately; failures and restarts reuse the original and resume removal. Both stages run on the configured ComfyUI endpoint. Uploading the original for removal also leaves an input copy on that server, so include those files in your normal ComfyUI storage cleanup after the session completes.

Validate a small batch before launching all 10,000: inspect transparency on light and dark backgrounds, especially around hair, glasses, and clothing. The automated checks verify PNG headers, RGBA output and matching dimensions; they do not judge mask quality.

## Generation dashboard

The launchers open a Textual dashboard with separate prompt and image panels. Each panel shows progress, its current job and a scrolling activity log. Panels stack on narrower terminals. The LLM worker prepares prompts while the ComfyUI worker renders the previous completed prompt. Blocking HTTP requests run on separate threads, leaving the UI responsive. Only one image is submitted at a time.

| Control | Action |
| --- | --- |
| **Space** / Pause / Resume | Stop taking new jobs; active requests finish and save their results. Resume continues both workers. |
| **R** / Retry failures | Requeue failed jobs and resume. Existing prompts and ComfyUI job IDs are retained. |
| **Shift+R** | Resubmit failed jobs with their saved prompts and seeds if ComfyUI lost their history. May duplicate server work if the old job is still running. |
| **Q**, **Ctrl+C** / Save & exit | Finish active requests, save state, and close. Run the same command later to resume automatically. |

`generation.prompt_queue_size` limits the number of ready prompts waiting on images (default 64). When full, the LLM worker waits for space. A service error in the image worker pauses dispatch, displays the failure, and preserves the job for retry. LLM rewrite errors still fall back to the original validated template and appear in the prompt log.

State lives in `session.sqlite3` beside `images/` and `prompts/`. Keep this file with the dataset to resume reliably. The publisher exports `image`, `image_transparent`, and `prompt`. A session lock prevents two processes writing the same output directory. Existing `img/` and `prompt/` directories are automatically moved to `images/original/` and `prompts/`; conflicting files stop migration rather than overwrite data. Existing originals are reused and queued for missing transparent versions. A portrait is complete only when both images and its prompt are saved. Batch size and seed must match the saved session.

ComfyUI submission IDs are saved immediately after acknowledgement, so restart and timeout retries retrieve that job instead of intentionally submitting it again. Keep the ComfyUI server/history available until downloads finish. An abrupt process kill in the small interval between server acceptance and acknowledgement can leave an orphan render on the server; local output still has one original, one transparent image and one prompt per sample. Save & exit avoids this interruption window. If the server has lost a saved job/history, let the retrieval time out, then use Shift+R to resubmit failed jobs. Active requests may take up to the configured service timeout (plus an in-progress HTTP request) to drain.

Run the offline regression suite with:

```bash
uv run --locked python -m unittest discover -s tests -v
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

The publisher uses the optional `publish` dependencies. It skips records whose transparent version or nonempty prompt is missing. The `body` split contains both images and their shared prompt.

```bash
uv run --locked --extra publish python publish_data_set.py --path ./dataset/idPhoto --user your_username --dataset_name your_dataset_name
```

The [hosted dataset](https://huggingface.co/datasets/lambdaWalker/ds.photo_id) has its own dataset card and license information.

## Portrait trait sampling

Face outlines are sampled uniformly across ten descriptive profiles. Each profile specifies a compatible forehead, cheek contour and jaw. These are prompt design categories with overlapping boundaries. Skin depth and undertone, eye contour, eyelid crease and spacing, brow density and curve, nose bridge and tip, mouth width and lip shape, and ear size and lobes are sampled separately. Hair textures also have equal probability.

The template includes those sampled facial details. The LLM must preserve their phrases and exact age. Facial asymmetry and other optional facial details have a 25% sampling probability, and skin texture details use the existing 10% probability. These choices prioritize visual coverage. Only the age distribution is calibrated to U.S. Census counts.

Face-outline terminology was cross-checked against the [LGBT Health and Wellbeing makeup guide](https://www.lgbthealth.org.uk/wp-content/uploads/2018/03/T-TIME-MAKE-UP-GUIDE.pdf). Rendering and visual review are needed to measure the diversity actually produced by the model.

## Coordinated clothing

Portraits sample casual, knitwear, smart and workwear outfits. Base garments, optional open layers and accessories receive separate colors from 24 curated palettes in four groups. These palettes are design choices for visual variety. Each garment/color pairing must survive the LLM rewrite.

Preview reproducible combinations with the standalone script.

```bash
uv run --locked python preview_clothing.py --count 20 --seed 42
uv run --locked python preview_clothing.py --count 10 --palette "muted contrast"
```

The preview prints JSON with garment roles, colors, palette names and the final clothing description. Available palette groups are neutral, tonal, muted contrast and bright accent.
