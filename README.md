# Photo ID Dataset Generator

Generate synthetic ID-style portraits using Qwen Image 2.1 in ComfyUI. Each dataset row contains both image variants and their shared prompt.

| Column | Type | Contents |
| --- | --- | --- |
| `image` | Image | The original generated portrait. |
| `image_transparent` | Image | The same portrait with an RGBA transparent background. |
| `prompt` | String | The original generation prompt saved with that portrait. |
| `parameters` | String (JSON) | Structured subject traits and generation settings; null for older exports without a sidecar. |

## Generate portraits

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and start a ComfyUI build that supports `TextEncodeQwenImage21` and `QwenImage21Cache`. The API graph in `res/qwen_image_2_1_api.json` uses the supplied workflow's Qwen UNet, text encoder and VAE. Install those exact model files on the ComfyUI server or adjust their names in the graph.

On Linux or macOS, run `./run.sh`. On Windows, run `run.bat` (or `.\run.bat` in PowerShell). Both launchers use the locked uv environment and forward generator arguments such as `--config path/to/config.yaml`.

Edit `config.yaml` to set the ComfyUI URL, the local LLM's OpenAI-compatible API base URL and model ID, and the batch size, seed, and output directory. For a smoke test, set `generation.samples` to a small number and use a separate output directory. Set `llm.enabled: false` to use the template directly.

The external LLM edits the sampled description at low temperature. The generator checks that the sampled phrases and exact age survive, falls back to the template on a failed check or request, and appends the fixed framing. The API graph bypasses the supplied editor workflow's optional in-graph prompt refiner and uses the built-in PNG saver. Seeds are repeatable for the same batch settings. Each output directory is a resumable session. Its sampled descriptions, required traits, image seeds, completed prompts, and workflow are saved once. Use a fresh output directory to change batch size, seed, workflow, or sampled prompt settings. Endpoint settings can be changed between runs; an already-submitted image is polled on its original server.

The generator saves the original before running BiRefNet on the ComfyUI server. It then saves a transparent image with matching dimensions (WebP by default, optionally PNG). Both images share the exact positive prompt sent to Qwen and are matched by filename stem.

```text
dataset/idPhoto/
├── original/
│   └── photoId_00001.webp
├── transparent/
│   └── photoId_00001.webp
├── prompts/
│   └── photoId_00001.txt
├── parameters/
│   └── photoId_00001.json
└── session.sqlite3
```

## ID portrait framing

The positive prompt begins with fixed camera composition: a tight, straight-on headshot, crown-to-chin height around two thirds of the image, a small margin over the head, and upper shoulders reaching beyond the side edges. Clothing descriptions apply only to the neckline and upper shoulders. The LLM edits subject traits separately, then the fixed composition is prepended. Negative conditioning excludes waist-up, mid-body and distant shots.

Restarting upgrades completed prompts that have not been submitted and have no original image yet. Submitted jobs and existing image/prompt records retain their original prompt. The full diagnostic UI workflow uses the same framing. These are model instructions rather than measured crop enforcement; review a small fresh batch on your server before generating the full dataset.

## Image storage

The supplied configuration saves **WebP at quality 90** for both image variants, preserving transparency. Configure `generation.image_storage.format` (`webp` or `png`), `quality` (0–100), and `lossless` (true/false). Encoding uses Pillow locally after PNG downloads. Changing the setting applies to missing/new images; existing PNGs remain intact and mixed PNG/WebP sessions resume normally. File paths and encoding settings are included in parameter JSON. Avoid keeping both PNG and WebP copies with the same stem in the same variant folder.

Clean server-side ComfyUI images manually after both local variants and their parameters JSON are saved. No cleanup extension or cleanup token is used. Server output names include unique request suffixes to prevent cached SaveImage results from referring to previously deleted files; local dataset stems stay unchanged.

## Structured generation parameters

Every generated portrait has a matching `parameters/photoId_00001.json` record (`schema_version: 1`). This is intended as input to later fictional name, address and ID-detail generators. It contains:

- `sample`: the complete sampled age, gender label, ancestry category, skin, face, eyes, hair, clothing/palette/pieces and accessories. These are intended synthetic generation inputs, not verified attributes measured from the image. Some sampled context (such as ancestry) is not rendered explicitly in the portrait prompt.
- `prompt_seed`, `image_seed`, and batch size/seed; draft, required phrases and exact final positive prompt.
- `prompt_finalization`: LLM model/API, thinking and temperature settings, and whether the final text was rewritten or the template was retained.
- `image_workflow`: the actual submitted Qwen graph, including model filenames, sampler, scheduler, dimensions, seed, steps, CFG and negative prompt; `image_requested_at` is its UTC submission-attempt time.
- `background_removal`: the saved removal graph and logical original-image path. Its upload filename is assigned separately on the server.
- `files`: relative paths linking both images and the shared text prompt.

Traits and prompt seeds are captured once at sampling and retained in SQLite. JSON is written atomically when prompts become ready and before each new image/removal submission. Restarting also exports records for existing originals. Older sessions did not save structured traits or actual execution settings: their records explicitly use `provenance: legacy_partial`, null sampled data and a missing-history explanation. They are never resampled or guessed from the image; new execution settings are added only when a new request is made. Updating this code cannot recover historical data that was not recorded.

The web explorer links to each JSON record. The upload worker includes it as a JSON string in `parameters` so downstream consumers can call `json.loads(record['parameters'])`. Records are uploaded only after their image/prompt files and JSON are complete and consistent. No names, addresses, birth dates or document numbers are generated at this stage.

## Background removal setup

On the **ComfyUI machine** (your DGX Spark), update ComfyUI to a build that includes `LoadBackgroundRemovalModel` and `RemoveBackground`. Download [birefnet.safetensors](https://huggingface.co/Comfy-Org/BiRefNet/resolve/main/background_removal/birefnet.safetensors) into `ComfyUI/models/background_removal/` and restart ComfyUI. No segmentation model is loaded by the Textual client.

The separate `res/birefnet_api.json` graph follows the [official native BiRefNet workflow](https://docs.comfy.org/tutorials/utility/remove-background-birefnet): load the saved original, predict the mask, invert it for `JoinImageWithAlpha`, and save RGBA PNG. It retains soft mask edges and the original dimensions. The graph is snapshotted into each session on first use. Select a different model filename in that graph before creating a new session if needed.

Original generation and background removal run sequentially in the image worker while the LLM worker continues preparing prompts. The original is committed locally before the removal workflow is submitted. Background job IDs are saved separately; failures and restarts reuse the original and resume removal. Both stages run on the configured ComfyUI endpoint. Uploading the original for removal also leaves an input copy on that server, so include those files in your normal ComfyUI storage cleanup after the session completes.

Validate a small batch before launching all 10,000: inspect transparency on light and dark backgrounds, especially around hair, glasses, and clothing. The automated checks verify PNG headers, RGBA output and matching dimensions; they do not judge mask quality.

## Drag-and-drop ComfyUI diagnostics

These are **UI workflows**, unlike the `*_api.json` graphs submitted by the Python client. Drag either file onto the ComfyUI canvas:

- [`res/check_photo_pipeline_ui.json`](res/check_photo_pipeline_ui.json): full Qwen 2.1 generation, original PNG saving, BiRefNet removal, and transparent PNG saving. A fixed sample prompt generates one 512×512 portrait in 20 steps.
- [`res/check_birefnet_ui.json`](res/check_birefnet_ui.json): background removal only. Upload an existing portrait in `LoadImage`, select the BiRefNet weights, and run.

All nodes are expanded so missing node types are visible on import. If a node is available but its weights are missing, select an installed model in its loader; pressing **Run** validates the selections and tests execution. Pay particular attention to `TextEncodeQwenImage21`, `QwenImage21Cache`, `LoadBackgroundRemovalModel`, and `RemoveBackground`.

Both workflows save test outputs under `ComfyUI/output/diagnostics/`. They do not modify the generator's dataset or saved session. Their JSON connections have been checked offline; execution still needs verification on your ComfyUI server.

## Generation dashboard

The launchers open a Textual dashboard with separate prompt and image panels. Each panel uses compact status rows so most of its height is available to the scrolling activity log, with up to 2,000 retained lines. Press **D** to show or hide connection URLs and the dataset path. Panels stack on narrower terminals. The LLM worker prepares prompts while the ComfyUI worker renders the previous completed prompt. Blocking HTTP requests run on separate threads, leaving the UI responsive. Only one image is submitted at a time.

| Control | Action |
| --- | --- |
| **Space** / Pause / Resume | Stop taking new jobs; active requests finish and save their results. Resume continues both workers. |
| **R** / Retry failures | Requeue failed jobs and resume. Existing prompts and ComfyUI job IDs are retained. |
| **Shift+R** | Resubmit failed jobs with their saved prompts and seeds if ComfyUI lost their history. May duplicate server work if the old job is still running. |
| **Q**, **Ctrl+C** / Save & exit | Finish active requests, save state, and close. Run the same command later to resume automatically. |

`generation.prompt_queue_size: null` (the default) lets the LLM prepare the entire batch independently. Each finished prompt is immediately committed to `prompts/`, its structured record is written to `parameters/`, and SQLite records it as ready for the image worker. Both workers still run concurrently and resume from disk. An optional positive queue size can limit how far the LLM runs ahead; only that setting makes it wait for queue space. A service error in the image worker pauses dispatch, displays the failure, and preserves the job for retry. LLM rewrite errors still fall back to the original validated template and appear in the prompt log.

State lives in `session.sqlite3` beside `original/`, `transparent/`, and `prompts/`. Keep this file with the dataset to resume reliably. Incremental uploads include `id`, `image`, `image_transparent`, `prompt`, and `parameters`. A session lock prevents two processes writing the same output directory. Existing `img/` and `prompt/` directories are automatically moved to `original/` and `prompts/`; conflicting files stop migration rather than overwrite data. The previous nested `images/original/` and `images/transparent/` folders also migrate to the flat layout. Existing originals are reused and queued for missing transparent versions. A portrait is complete only when both images and its prompt are saved. Batch size and seed must match the saved session.

ComfyUI submission IDs are saved immediately after acknowledgement, so restart and timeout retries retrieve that job instead of intentionally submitting it again. Keep the ComfyUI server/history available until downloads finish. An abrupt process kill in the small interval between server acceptance and acknowledgement can leave an orphan render on the server; local output still has one original, one transparent image and one prompt per sample. Save & exit avoids this interruption window. If the server has lost a saved job/history, let the retrieval time out, then use Shift+R to resubmit failed jobs. Active requests may take up to the configured service timeout (plus an in-progress HTTP request) to drain.

Run the offline regression suite with:

```bash
uv run --locked python -m unittest discover -s tests -v
```

## Web dashboard

The supplied configuration enables a browser companion at **http://127.0.0.1:8765** while the terminal app runs. Both interfaces control the same session and workers. The terminal header and image log show the dashboard URL. Set `web.enabled: false` to disable the companion, or change `web.port` if the port is already in use. The host defaults to the local machine; open the browser on the machine running this Python app.

To run only the browser interface:

```bash
./run.sh --web
# Windows: run.bat --web
```

Keep that command running and open the displayed URL. Use Ctrl+C in its console to drain active work and close the server; closing a browser tab leaves processing running. Terminal and browser modes acquire the same session lock, so launch one generator process and connect as many browser tabs as needed.

The dashboard has separate prompt and image progress panels with ETAs, current jobs, scrolling logs and shared Pause/Resume and Retry controls. Logs update every second and preserve your scroll position when you scroll back. The dataset explorer shows the **latest four saved originals**, newest first, with matching transparent images on a checkerboard, prompts, and errors. Transparent versions appear as soon as removal finishes. Click either image for a full-size view. Existing generations remain available on restart; activity logs cover the current process only. The web server adds no Python dependencies and serves only the dashboard, its state, PNG images and parameter JSON records.

## Time estimates

Each panel distinguishes **active work left** (processing time excluding waits), **average seconds per item**, and **finish ETA** (including pipeline waits). When the ready queue is full, the faster LLM waits for image processing to free a slot, so its finish ETA can be almost the same as the image worker even though its active work is much shorter. The web worker status explicitly reports this as “Waiting for queue space”. The image ETA estimates completion of the remaining batch, including original generation, background removal and prompt availability. With the default unlimited disk queue, prompt finish ETA reflects LLM processing time alone. An optional positive queue cap also accounts for time waiting on the image worker. Estimates use the last 30 successful timings per stage, saved in the session database across restarts. Queue waits, idle periods and failures are excluded from those averages; retrieving already-submitted remote jobs does not train a new image-stage average.

Expect “measuring…” until the needed stages have completed. Initial model loading and changing server load can make early estimates inaccurate. While paused, the row shows estimated processing time **on resume**, rather than a promised wall-clock finish time. Active requests continue to drain normally. These are approximate throughput estimates, not deadlines.

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

## Incremental Hugging Face uploads

A third independent worker uploads completed records while prompts and images continue. The supplied configuration enables it for **`lambdaWalker/ds.photo-id`**, separate from the older full-export dataset. It creates a **private** dataset on its first successful upload. Set `huggingface.repo_id` to a dataset you can write, and set `private: false` before first creation if you want a public dataset. This setting does not change the visibility of an existing repository.

Sign in once using the account that owns that dataset (or has write access):

```bash
uv run --locked hf auth login
```

Credentials use Hugging Face's saved login; no token is stored in YAML or the dataset. Then run the usual `run.bat` / `./run.sh` or browser-only mode. To disable uploads, set `huggingface.enabled: false`.

| Setting | Default | Meaning |
| --- | --- | --- |
| `batch_size` | 10 | Upload after this many complete records accumulate. |
| `interval_seconds` | 300 | Upload a smaller batch after five minutes of pending data. |
| `retry_seconds` | 60 | Retry failed uploads after one minute. |

Each row contains `id`, `image`, `image_transparent`, `prompt`, and `parameters` (JSON text). Both PNG/WebP image byte streams are embedded in Parquet; loading the dataset does not depend on your local paths. Row IDs combine a durable session UUID and the portrait stem so separate sessions do not collide.

Only records with both images and saved parameters are eligible. New immutable shards are committed under `data/train/`. SQLite tracks batch membership, remote filenames and acknowledgements; interrupted uploads retry the same staged bytes at the same remote path. Keep `session.sqlite3` and the `uploads/` staging folder with the dataset until pending uploads succeed. Successful staging files are removed locally, while original images and metadata remain. Reopening a session catches up with existing completed records without duplicating acknowledged batches. Remote history deletion or manually removing uploaded shards is not automatically repaired.

Both dashboards have a dedicated **Hugging Face panel** with its own progress bar, uploaded/pending counts, current batch and record count, processing phase, retry countdown, and scrolling error/activity log. Upload phases distinguish preparing a shard, creating/checking the dataset, checking repository layout, and uploading/committing. The uploader owns a separate asyncio task; Parquet encoding and Hub requests run in worker threads so prompts, images and UI updates continue during slow uploads. Press **U** in the terminal or **Retry upload** in the browser to bypass the retry countdown (resume first if paused). The terminal shows three columns on wide windows and stacks panels in narrower windows. During shutdown it explicitly reports when it is draining uploads. Network/login failures never pause image generation. Pause prevents starting another upload; an active upload finishes. Save & exit drains generation and then tries to upload all remaining records, including a partial final batch. If that attempt fails, data stays queued for the next run. Upload requests can extend shutdown time. The Hub dataset viewer may refresh later than the commit itself.

Use a dedicated empty repository or one created by this uploader. It refuses to mix shards into an older dataset layout. Existing dataset cards are preserved; first-time setup adds a card describing the `train` split. The uploader itself never changes or deletes existing remote shards.

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

## Project entry points

- `run.bat` / `run.sh`: supported launchers; `--web` selects browser-only mode. Both call `photo_id_generator.py`.
- `preview_clothing.py`: inspect sampled clothing and color combinations without generation.
- `generation_session.py`, `generation_ui.py`, `web_dashboard.py`, and `incremental_upload.py`: runtime modules used by the launchers.
- `res/check_*_ui.json`: current drag-and-drop ComfyUI diagnostics; the other Qwen/BiRefNet JSON files are runtime API graphs.
- `tests/`: offline regression suite.

The obsolete Flux graph, separate full-dataset publishing script, and token-based server cleanup extension have been removed. Existing session databases and generated files do not need migration for this cleanup.
