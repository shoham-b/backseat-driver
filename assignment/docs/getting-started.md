# Getting Started

## Docker Compose (recommended)

The fastest way to run the full stack — no prerequisites beyond Docker:

```bash
docker compose up
```

This starts:

| Service | Port | Description |
|---|---|---|
| **api** | `:8080` | VLM Scene Description HTTP API |

The API is ready when you see `Application startup complete` in the logs.

## Local development

**Prerequisites:**

| Tool | Install | Purpose |
|---|---|---|
| [Python 3.13+](https://www.python.org/) | system / pyenv | Runtime |
| [uv](https://docs.astral.sh/uv/) | `curl -LsSf https://astral.sh/uv/install.sh \| sh` | Package manager and script runner |
| [just](https://github.com/casey/just) | `cargo install just` / `brew install just` | Dev task runner |

**Setup:**

```bash
git clone <repo-url>
cd vlm_scene_description
uv sync --group dev         # install all deps including dev tools
uv run pre-commit install   # register git hooks (ruff + mypy on every commit)
cp .env.example .env        # create local config (gitignored)
```

**Start the dev server with hot reload:**

```bash
just dev
```

The API is available at `http://127.0.0.1:8080`. Open `http://127.0.0.1:8080/docs` for interactive Swagger UI.

## Exploring the API

Once the stack is running, three interactive interfaces are available:

| Interface | URL | Description |
|---|---|---|
| Swagger UI | `http://127.0.0.1:8080/docs` | Browse endpoints, inspect schemas, try requests |
| ReDoc | `http://127.0.0.1:8080/redoc` | Read-only reference |
| OpenAPI schema | `http://127.0.0.1:8080/openapi.json` | Machine-readable spec |

**Health check:**

```bash
curl http://127.0.0.1:8080/health
# {"status": "ok"}
```

## Configuration

All settings are prefixed with `VLM_SCENE_DESCRIPTION_`. Copy `.env.example` to `.env` and override as needed:

| Variable | Default | Description |
|---|---|---|
| `VLM_SCENE_DESCRIPTION_API_HOST` | `127.0.0.1` | API bind address |
| `VLM_SCENE_DESCRIPTION_API_PORT` | `8080` | API bind port |
| `VLM_SCENE_DESCRIPTION_DB_BACKEND` | `memory` | Storage backend (`memory` or `sqlite`) |
| `VLM_SCENE_DESCRIPTION_DB_PATH` | `vlm_scene_description.db` | SQLite database path (when `DB_BACKEND=sqlite`) |
| `VLM_SCENE_DESCRIPTION_LOG_FORMAT` | `colored` | Log output: `colored` (ANSI, for terminals) or `json` (one object per line, for log aggregators) |

See [`vlm_scene_description/config.py`](../vlm_scene_description/config.py) for the full settings class and defaults.
