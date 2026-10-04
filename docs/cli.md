# CLI Reference

All commands are run via `uv run backseat-driver <command>`. `bd` is a shorter alias for the same entry point, so `uv run bd <command>` works too.

Global help: `uv run backseat-driver --help`

---

## `--version` / `-V`

Print the installed version and exit.

```bash
uv run backseat-driver --version
# backseat-driver 0.1.0
```

---

## `run`

Describe every scene in a nuScenes dataset and write the results to JSON. This is the pipeline the
assignment asks for.

```bash
uv run backseat-driver run [OPTIONS]
```

| Option | Env var | Default | Description |
|---|---|---|---|
| `--dataroot` | `BACKSEAT_DRIVER_NUSCENES_DATAROOT` | `data/sets/nuscenes` | Path to the local dataset |
| `--version` | `BACKSEAT_DRIVER_NUSCENES_VERSION` | `v1.0-mini` | nuScenes dataset version |
| `--camera` | — | one of `--camera`/`--all-cameras` is required | Camera channel used as the representative frame, e.g. `CAM_FRONT`. Repeat it (`--camera CAM_FRONT --camera CAM_BACK`) to describe several cameras |
| `--all-cameras` | — | — | Describe all six cameras (`CAM_FRONT`, `CAM_FRONT_RIGHT`, `CAM_BACK_RIGHT`, `CAM_BACK`, `CAM_BACK_LEFT`, `CAM_FRONT_LEFT`) of every scene. Cannot be combined with `--camera` |
| `--backend` | `BACKSEAT_DRIVER_VLM_BACKEND` | `huggingface` | `huggingface` (terse BLIP captions) , `ollama` (needs a running Ollama server) or `anthropic` (hosted Claude; needs `..._ANTHROPIC_API_KEY`) — the last two give verbose, prompt-driven descriptions |
| `--model` | `BACKSEAT_DRIVER_VLM_MODEL_NAME` / `..._OLLAMA_MODEL_NAME` / `..._ANTHROPIC_MODEL_NAME` | **required** (no default) | Model for the chosen backend, e.g. `Salesforce/blip-image-captioning-base`, `llava`, `claude-haiku-4-5-20251001`. Fails fast if neither the flag nor the variable is set |
| `--output` | — | `<output dir>/<backend>__<model>.json` | Where to write the JSON results. By default inferred from the backend and model (see below); the directory is `BACKSEAT_DRIVER_OUTPUT_DIR` (default `output`) |
| `--max-scenes` | — | (all scenes) | Only process the first N scenes (all of a scene's cameras count as one) |

**Examples:**

```bash
# Full v1.0-mini run on the front camera
uv run backseat-driver run --camera CAM_FRONT --model Salesforce/blip-image-captioning-base

# Pick the backend and model; the output file is inferred
uv run backseat-driver run --camera CAM_FRONT --backend ollama --model llava:13b
# -> output/ollama__llava-13b.json

# Quick check against the first 2 scenes only
uv run backseat-driver run --camera CAM_FRONT --model Salesforce/blip-image-captioning-base --max-scenes 2

# Different dataset location and camera
uv run backseat-driver run --dataroot /mnt/nuscenes --camera CAM_BACK --model Salesforce/blip-image-captioning-base

# Every camera of every scene, in one result file
uv run backseat-driver run --all-cameras --model Salesforce/blip-image-captioning-base
```

Each scene's output line during the run looks like:

```
  scene-0061: a busy city street with cars and pedestrians
```

---

## `report` and `ui`

Compare how several models described the same scenes. Takes the JSON files written by `run` (one per
model; default: every `*.json` in the output directory) and writes a single self-contained HTML page (images embedded, no server needed).

```bash
uv run backseat-driver run --camera CAM_FRONT --backend huggingface --model Salesforce/blip-image-captioning-base
uv run backseat-driver run --camera CAM_FRONT --backend ollama --model llava
uv run backseat-driver report        # every output/*.json -> output/report.html
```

The page lets you filter by scene, model, camera and description text. Each card is one scene seen through one camera and is labelled with the camera position (e.g. "Front left"); the camera filter appears when the results cover more than one. It shows every model's description
next to the keyframe, and tabulates precision / recall / F1 / average length per model (recomputed
for the scenes currently shown).

**How accuracy is measured.** Each description is scored against the human-written nuScenes scene
label (e.g. "Parked truck, construction, intersection") by content-word overlap — stopwords
removed, plurals folded, words found in the label highlighted. Precision is the share of the model's
words found in the label, recall the share of the label's words the model mentioned. Synonyms don't
match and verbose models score low on precision, so read the numbers as a relative signal between
models rather than absolute accuracy. Results produced before this feature carry no label and are
shown unscored; re-run `run` to get scores.

### The UI (`just ui`)

Same page, served locally instead of written to a file. It is not a CLI command but a small FastAPI app, run like the API: `just ui` is `fastapi run backseat_driver/reporting/ui_server.py` on `BACKSEAT_DRIVER_UI_HOST`/`_UI_PORT`. It shows every `*.json` in the output directory (`BACKSEAT_DRIVER_OUTPUT_DIR`), re-read on every page load, and refuses to start if there are none and `BACKSEAT_DRIVER_UI_ALL_JOBS` is off.

```bash
just ui                                       # all JSON files in output/
BACKSEAT_DRIVER_UI_ALL_JOBS=true just ui      # ...plus every completed job on the API
```

### Reports from the API

`report` can read finished jobs from the API instead of (or as well as) result files: pass the id of a completed job with `--job`; each job is one model's run, so give several ids to compare models. The UI does the same with `BACKSEAT_DRIVER_UI_ALL_JOBS=true`, which shows every completed job on the API (the newest per model) and re-reads them on each page load, so no ids are needed and a job that finishes appears on the next refresh. The descriptions come from `GET /jobs/{id}/descriptions` and every image from `GET /images/{key}`, so the report needs the API and nothing else: no dataset on disk, no database, no bucket.

```bash
just dev                                                  # the API, as a monolith
curl -X POST localhost:8080/jobs                          # -> job_id; wait until it is completed
uv run backseat-driver report --job <job-id> [--job <other-job-id>] [--api-url http://localhost:8080]
BACKSEAT_DRIVER_UI_ALL_JOBS=true just ui                  # every completed job, refreshed on each load
```

The UI serves the images itself, forwarding each one to the API, so the browser only talks to the UI. It exposes `/`, `/images/<key>` and `/healthz`. `BACKSEAT_DRIVER_API_URL` is the API the UI process reads from; `BACKSEAT_DRIVER_UI_PUBLIC_API_URL` is where your browser reaches the API for the live-inference card, if that differs (the usual case in a cluster).

A job that is still running is an error rather than a partial report. When debugging as a monolith the jobs are kept in a SQLite file (`BACKSEAT_DRIVER_JOBS_DB_PATH`, default `output/jobs.db`), so ids and results survive a restart of the API.

## `dataset upload`

`backseat-driver dataset upload [--camera CAM_FRONT ...| --all-cameras] [--dataroot DIR] [--version v1.0-mini]` copies the dataset's metadata tables and the chosen cameras' images from a local dataroot into the dataset bucket (`BACKSEAT_DRIVER_DATASET_BUCKET`), once, for the distributed mode. Reruns replace the tables and skip images already there. Without `--camera` it uploads the configured camera. Not needed when debugging as a monolith.

## `worker`

`backseat-driver worker ingest|caption` run the distributed queue workers. `worker ingest --once` handles a single queued ingest task and exits, for the Kubernetes Job that KEDA starts per task.

| Option | Default | Description |
|---|---|---|
| `--host` | `127.0.0.1` | Interface to serve on |
| `--port` | `8081` | Port to serve on |
| `--open/--no-open` | `--open` | Open the page in a browser |

The page is rebuilt from the files on each start; restart after a new `run`.

---

## `test smoke`

Run the smoke test suite against a live API.

```bash
uv run backseat-driver test smoke [OPTIONS]
```

| Option | Env var | Default | Description |
|---|---|---|---|
| `--api-url` | `API_URL` | `http://127.0.0.1:8080` | Base URL of the running API |
| `--verbose` / `-v` | — | off | Pass `-v` to pytest |

**Examples:**

```bash
# Against the local dev server
uv run backseat-driver test smoke

# Against a remote target
uv run backseat-driver test smoke --api-url https://staging.example.com

# Via environment variable
API_URL=https://staging.example.com uv run backseat-driver test smoke --verbose
```

Exits with the pytest exit code. Exits `0` when all tests pass or when no smoke tests are collected yet.
