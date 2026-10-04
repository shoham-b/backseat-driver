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
| `just dev` | API dev server with hot reload (`fastapi dev`) in monolith mode: `/jobs` runs in-process, no infra needed |
| `just dev-distributed` | Same, but distributed mode against RabbitMQ + Postgres in Docker (starts them); pair with `just worker-*` |
| `just serve` | API production-mode server on the host, binds `0.0.0.0` (monolith unless `BACKSEAT_DRIVER_MODE=distributed`) |
| `just infra` / `just infra-down` | RabbitMQ + Postgres in Docker for the host-run API and workers |
| `just worker-ingest` / `just worker-caption` | Queue workers on the host |
| `just docker-run [ARGS]` | The pipeline in the `cli` container |
| `just up` / `just up-dev` / `just down` | Full distributed stack in Docker Compose (`up-dev` hot-reloads the API) |
| `just k8s-render` / `k8s-validate` / `k8s-apply` / `k8s-delete` | Kubernetes manifests in `deploy/k8s` |
| `just k8s-up` / `k8s-status` / `k8s-down` | Local kind cluster with KEDA queue-depth autoscaling (`deploy/kind`) |
| `just test` | Unit + integration tests with coverage |
| `just test-smoke` | Smoke tests against a running API |
| `just test-ui` | Selenium tests of the model-comparison UI (needs Chrome) |
| `just test-system` | Full system test via Docker Compose (builds images, tears down after) |
| `just test-all` | `just test` followed by `just test-system` |
| `just bench` | Performance benchmarks (pytest-codspeed) |
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
| Unit | `tests/unittests/` | none — nuscenes-devkit/transformers are replaced by injected fakes, no dataset or model download |
| Integration | `tests/integrationtests/` | in-process API (no external services); captioner is swapped for a fake |
| Smoke | `tests/smoketests/` | running API (pass `--api-url` to override) |
| UI | `tests/uitests/` | headless Chrome + Selenium; starts the real `ui` server itself |
| System | `tests/systemtests/` | Docker Compose |

### Unit tests

```bash
uv run pytest tests/unittests -v
```

No I/O, no network, no GPU. `scenes/nuscenes_scene_loader.py` and `captioning/huggingface_backend.py` import nuscenes-devkit and
transformers lazily inside their default factories, which the loader and backend take as constructor arguments so these tests can pass a fake — see
`tests/unittests/test_nuscenes_scene_loader.py` and `test_huggingface_backend.py`.

### Integration tests

```bash
just test   # unit + integration with coverage
# or
uv run pytest tests/integrationtests -v
```

FastAPI runs in-process via `httpx.ASGITransport` — no port binding, no subprocess, and the real
`BackendCaptioner` is swapped for a `FakeCaptioner` fixture so tests don't download model weights.

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
just test-system
```

Builds the images, starts the stack (API, RabbitMQ, Postgres), runs `tests/systemtests/` and `tests/smoketests/` inside the
`systemtest` container, then tears everything down. Both `systemtest` and the `cli` service have
`profiles` set (`test` / `cli`) so neither starts with a plain `just compose up`.

To skip Docker and test an API that is already running (`just dev`, `just up`, a staging URL), pass its URL; only
`tests/systemtests/` runs, from the host:

```bash
just test-system-url http://localhost:8080   # works on Windows too
```

### Coverage

```bash
just test   # includes --cov; enforced in CI via `fail_under` in `pyproject.toml`
```

Coverage is measured over `backseat_driver` excluding `cli/`.

### Benchmarks

```bash
just bench   # or: uv run pytest tests/benchmarks --codspeed
```

`tests/benchmarks/` holds [pytest-codspeed](https://codspeed.io/docs/reference/pytest-codspeed) benchmarks
for the pipeline, the queue workers, queue-message (de)serialization, the JSON writer and nuScenes keyframe
selection. Like the unit tests they run against in-memory fakes, so they measure the code around the VLM, not
the model. The `CodSpeed` workflow runs them in CPU simulation mode on every push and pull request and reports
regressions on the PR. To measure locally the same way, install the [CodSpeed CLI](https://codspeed.io/docs/cli)
and run `codspeed run --mode simulation -- uv run pytest tests/benchmarks --codspeed`.

## Package structure

```
backseat_driver/
├── api/            # Optional FastAPI service (/describe, /health, /ready)
│   └── routers/
├── captioning/     # Captioner port, CaptionBackend (HuggingFace/Ollama/Anthropic) + CaptionModel, build_captioner
├── scenes/         # SceneLoader port + nuScenes loader, ScenePipeline, JSON writer
├── jobs/           # JobQueue/JobStore ports + Celery/Postgres implementations, ORM, workers
├── errors.py       # BackseatDriverError hierarchy
├── cli/            # Typer CLI — `run` (the pipeline) and `test smoke`
├── models/         # Shared domain models (pure Pydantic)
├── config.py       # Settings (pydantic-settings, env-var backed)
└── logger.py       # Loguru setup; LogFormat enum
tests/
├── unittests/
├── integrationtests/
├── smoketests/
├── uitests/
└── systemtests/
```

## Extending the pipeline

### Swapping the VLM

`captioning/captioner.py` defines a `Captioner` abstract class (`caption(image_path) -> str`, `healthcheck() -> bool`).
Subclass it in `backseat_driver/captioning/`, next to the existing backends (e.g. a different HF model, or a call to an external VLM API) and pass it
into `ScenePipeline` — nothing else needs to change.

### Adding an API endpoint

1. Add request/response models to `backseat_driver/models/` or directly in the router module.
2. Add domain logic to the matching capability package (`captioning/`, `scenes/`, `jobs/`).
3. Create or extend a router in `backseat_driver/api/routers/`.
4. Register the router in `backseat_driver/api/app.py`.
5. Add integration tests in `tests/integrationtests/`.

## Docker

```bash
just docker-run          # run the pipeline in the cli container
just up                  # API + RabbitMQ + Postgres + workers
just test-system        # system tests
```

Images are defined in `docker/Dockerfile` with named build targets: `cli` (default/primary) and `api`. See [Running it](running.md) for how every way of running the project fits together.

## Pre-commit hooks

```bash
uv run pre-commit install          # register
uv run pre-commit run --all-files  # run manually (= just check)
```

Hooks run ruff and ty on every commit. The CI workflow also runs `pip-audit` to check for known
security vulnerabilities in dependencies.
