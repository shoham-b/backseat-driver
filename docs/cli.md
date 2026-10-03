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

### `ui`

Same page, served locally instead of written to a file. With no arguments it uses every `*.json` in the
output directory; `just ui` is the shortcut.

```bash
uv run backseat-driver ui output/blip.json output/llava.json --port 8081
just ui                      # all JSON files in output/
```

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
