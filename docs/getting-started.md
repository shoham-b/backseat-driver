# Getting Started

## 1. Get the dataset

nuScenes requires a free registration and cannot be redistributed in this repo. Download **v1.0-mini** from
[nuscenes.org](https://www.nuscenes.org/nuscenes#download) and extract it so you end up with:

```
data/sets/nuscenes/
├── maps/
├── samples/
├── sweeps/
└── v1.0-mini/
```

`data/` is gitignored. The default dataroot is `data/sets/nuscenes` — override with `--dataroot` or
`BACKSEAT_DRIVER_NUSCENES_DATAROOT` if you keep it elsewhere.

## 2. Run the pipeline

**Local (uv):**

```bash
uv sync --group dev
uv run backseat-driver run
```

**Docker (no local Python needed beyond Docker itself):**

```bash
docker compose --profile cli run --rm cli
```

Both read `data/sets/nuscenes`, describe every scene's `CAM_FRONT` keyframe, and write
`output/scene_descriptions.json`. The first run downloads the VLM weights
(`Salesforce/blip-image-captioning-base` by default, ~1GB) from HuggingFace and caches them.

**Useful options** (`uv run backseat-driver run --help` for the full list):

| Option | Default | Description |
|---|---|---|
| `--dataroot` | `data/sets/nuscenes` | Path to the local dataset |
| `--version` | `v1.0-mini` | nuScenes dataset version |
| `--camera` | `CAM_FRONT` | Camera channel used as the representative frame |
| `--backend` | `huggingface` | `huggingface`, `ollama` or `anthropic` |
| `--model` | per backend | HuggingFace model, Ollama model (default `llava`) or Claude model (default `claude-haiku-4-5-20251001`) |
| `--output` | `output/scene_descriptions.json` | Where to write the JSON results |
| `--max-scenes` | (all) | Only process the first N scenes — handy for a quick smoke run |

## 3. (Optional) Run the HTTP API

The same captioning logic is also exposed as a small on-demand service — see
[Architecture → Deployment](architecture.md#deployment) for why this exists alongside the CLI.

```bash
docker compose up api
# or locally:
just dev
```

```bash
curl http://127.0.0.1:8080/health
# {"status": "ok"}

curl -F "image=@data/sets/nuscenes/samples/CAM_FRONT/some_image.jpg" http://127.0.0.1:8080/describe
# {"description": "...", "model_name": "Salesforce/blip-image-captioning-base"}
```

Open `http://127.0.0.1:8080/docs` for interactive Swagger UI.

## Local development prerequisites

| Tool | Install | Purpose |
|---|---|---|
| [Python 3.14+](https://www.python.org/) | system / pyenv | Runtime |
| [uv](https://docs.astral.sh/uv/) | `curl -LsSf https://astral.sh/uv/install.sh \| sh` | Package manager and script runner |
| [just](https://github.com/casey/just) | `cargo install just` / `brew install just` | Dev task runner |

```bash
git clone <repo-url>
cd backseat-driver
uv sync --group dev         # install all deps including dev tools
uv run pre-commit install   # register git hooks (ruff + ty on every commit)
cp .env.example .env        # create local config (gitignored)
```

## Configuration

All settings are prefixed with `BACKSEAT_DRIVER_`. Copy `.env.example` to `.env` and override as needed:

| Variable | Default | Description |
|---|---|---|
| `BACKSEAT_DRIVER_NUSCENES_DATAROOT` | `data/sets/nuscenes` | Path to the local dataset |
| `BACKSEAT_DRIVER_NUSCENES_VERSION` | `v1.0-mini` | Dataset version |
| `BACKSEAT_DRIVER_CAMERA_CHANNEL` | `CAM_FRONT` | Camera used as the representative frame |
| `BACKSEAT_DRIVER_VLM_BACKEND` | `huggingface` | `huggingface`, `ollama` or `anthropic` |
| `BACKSEAT_DRIVER_VLM_MODEL_NAME` | `Salesforce/blip-image-captioning-base` | HuggingFace image-to-text model |
| `BACKSEAT_DRIVER_OLLAMA_MODEL_NAME` | `llava` | Ollama model, when backend is `ollama` |
| `BACKSEAT_DRIVER_OLLAMA_URL` | `http://localhost:11434` | Ollama server URL |
| `BACKSEAT_DRIVER_ANTHROPIC_MODEL_NAME` | `claude-haiku-4-5-20251001` | Claude model, when backend is `anthropic` |
| `BACKSEAT_DRIVER_ANTHROPIC_API_KEY` | unset | Required for the `anthropic` backend; each caption is a billed request |
| `BACKSEAT_DRIVER_OUTPUT_PATH` | `output/scene_descriptions.json` | Pipeline output path |
| `BACKSEAT_DRIVER_API_HOST` / `_API_PORT` | `127.0.0.1` / `8080` | API bind address (optional API only) |
| `BACKSEAT_DRIVER_LOG_FORMAT` | `colored` | Log output: `colored` (ANSI, for terminals) or `json` (log aggregators) |

See [`backseat_driver/config.py`](../backseat_driver/config.py) for the full settings class.
