# Development Guide

## Prerequisites

| Tool | Install | Purpose |
|---|---|---|
| [Python 3.12+](https://www.python.org/) | system / pyenv | Runtime |
| [uv](https://docs.astral.sh/uv/) | `curl -LsSf https://astral.sh/uv/install.sh \| sh` | Package manager |
| [just](https://github.com/casey/just) | `cargo install just` / `brew install just` | Task runner |
| [Docker](https://www.docker.com/) | platform installer | Compose system tests |

## Setup

```bash
git clone <repo-url>
cd backseat-driver
uv sync --group dev         # install all deps + dev tools
uv run pre-commit install   # register git hooks
cp .env.example .env
```

## Available tasks

Run `just --list` at any time to see all targets. The full table:

| Command | Description |
|---|---|
| `just run [ARGS]` | Run the scene-description pipeline (`backseat-driver run`) |
| `just dev` | API dev server with hot reload (`fastapi dev`) — optional deployment mode |
| `just serve` | API production-mode server, binds `0.0.0.0:8080` |
| `just test` | Unit + integration tests with coverage |
| `just bench` | CodSpeed benchmarks (`tests/benchmarks/`) |
| `just test-smoke` | Smoke tests against a running API |
| `just test-system` | System tests (requires the API to be running locally) |
| `just test-compose` | Full system test via Docker Compose (builds images, tears down after) |
| `just test-all` | All non-smoke tests with coverage |
| `just lint` | Ruff check + format check (CI mode — no auto-fixes) |
| `just fmt` | Auto-fix and reformat |
| `just typecheck` | ty type check |
| `just check` | Pre-commit on all files |
| `just docs` | Build HTML docs with MkDocs |
| `just docs-open` | Serve docs with live reload (`mkdocs serve`) |
| `just sync` | `uv sync --group dev` |
| `just hooks` | Install pre-commit hooks |

## Code quality

```bash
just lint       # ruff check + format check (CI mode — no auto-fixes)
just fmt        # auto-fix and reformat
just typecheck  # ty check
just check      # pre-commit on all files (ruff + ty)
```

All three are enforced in CI.

## Tests

There are four test layers, from fastest to slowest:

| Layer | Path | Infrastructure |
|---|---|---|
| Unit | `tests/unittests/` | none — nuscenes-devkit/transformers are monkeypatched, no dataset or model download |
| Integration | `tests/integrationtests/` | in-process API (no external services); captioner is swapped for a fake |
| Smoke | `tests/smoketests/` | running API (set `API_URL` to override) |
| System | `tests/systemtests/` | Docker Compose |

### Unit tests

```bash
uv run pytest tests/unittests -v
```

No I/O, no network, no GPU. `adapters/nuscenes_scene_loader.py` and `adapters/huggingface_captioner.py` import nuscenes-devkit and
transformers lazily inside methods specifically so these tests can monkeypatch them out — see
`tests/unittests/test_nuscenes_scene_loader.py` and `test_huggingface_captioner.py`.

### Integration tests

```bash
just test   # unit + integration with coverage
# or
uv run pytest tests/integrationtests -v
```

FastAPI runs in-process via `httpx.ASGITransport` — no port binding, no subprocess, and the real
`HuggingFaceCaptioner` is swapped for a `FakeCaptioner` fixture so tests don't download model weights.

### Smoke tests

```bash
just test-smoke              # against http://127.0.0.1:8080 (default)
API_URL=http://staging:8080 just test-smoke   # against another target
```

Or via the CLI:

```bash
uv run backseat-driver test smoke --api-url http://staging:8080
```

### System tests (Docker Compose)

```bash
just test-compose
```

Builds the `api` image, starts it, runs `tests/systemtests/` and `tests/smoketests/` inside the
`systemtest` container, then tears everything down. Both `systemtest` and the `cli` service have
`profiles` set (`test` / `cli`) so neither starts with a plain `docker compose up`.

### Coverage

```bash
just test   # includes --cov; must stay above 80% (enforced in CI)
```

Coverage is measured over `backseat_driver` excluding `cli/`.

## Package structure

```
backseat_driver/
├── api/            # Optional FastAPI service (/describe, /health, /ready)
│   └── routers/
├── bl/             # Business logic and the abstract ports it depends on: pipeline, workers, writer, errors
├── adapters/       # Concrete platform implementations of the bl/ ports (nuScenes, HuggingFace, Ollama, Anthropic, Celery, Postgres)
├── cli/            # Typer CLI — `run` (the pipeline) and `test smoke`
├── models/         # Shared domain models (pure Pydantic)
├── config.py       # Settings (pydantic-settings, env-var backed)
└── logger.py       # Loguru setup; LogFormat enum
tests/
├── unittests/
├── integrationtests/
├── smoketests/
└── systemtests/
```

## Extending the pipeline

### Swapping the VLM

`bl/captioner.py` defines a `Captioner` abstract class (`caption(image_path) -> str`, `healthcheck() -> bool`).
Subclass it under `backseat_driver/adapters/` (e.g. a different HF model, or a call to an external VLM API) and pass it
into `ScenePipeline` — nothing else needs to change.

### Adding an API endpoint

1. Add request/response models to `backseat_driver/models/` or directly in the router module.
2. Add business logic to `backseat_driver/bl/`.
3. Create or extend a router in `backseat_driver/api/routers/`.
4. Register the router in `backseat_driver/api/app.py`.
5. Add integration tests in `tests/integrationtests/`.

## Docker

```bash
docker compose --profile cli run --rm cli   # run the pipeline
docker compose up api                       # optional HTTP API
docker compose --profile test up            # system tests
```

Images are defined in `docker/Dockerfile` with named build targets: `cli` (default/primary) and `api`.

## Pre-commit hooks

```bash
uv run pre-commit install          # register
uv run pre-commit run --all-files  # run manually (= just check)
```

Hooks run ruff and ty on every commit. The CI workflow also runs `pip-audit` to check for known
security vulnerabilities in dependencies.
