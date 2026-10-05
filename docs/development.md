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
git clone https://github.com/shoham-b/backseat-driver.git
cd backseat-driver
uv sync --group dev         # install all deps + dev tools
uv run pre-commit install   # register git hooks
cp .env.example .env
```

## Available tasks

Run `just --list` at any time to see all targets. The full table:

| Command | Description |
|---|---|
| `just describe [ARGS]` | Run the scene-description pipeline (`backseat-driver describe`) |
| `just dev` | API dev server with hot reload (`fastapi dev`) in monolith mode: `/jobs` runs in-process, no infra needed |
| `just dev-distributed` | Same, but distributed mode against RabbitMQ + Postgres in Docker (starts them); pair with `just worker-*` |
| `just serve` | API production-mode server on the host, binds `0.0.0.0` (monolith unless `BACKSEAT_DRIVER_MODE=distributed`) |
| `just infra` / `just infra-down` | RabbitMQ + Postgres + a dev S3 store in Docker for the host-run API and workers |
| `just dataset-upload` | Copy `data/` into the dev S3 bucket, once, before `just worker-ingest` |
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

There are five test layers, from fastest to slowest:

| Layer | Path | Infrastructure |
|---|---|---|
| Unit | `tests/unittests/` | none — nuscenes-devkit/transformers are replaced by injected fakes, no dataset or model download |
| Integration | `tests/integrationtests/` | in-process API, CLI commands and ingest/caption workers (no external services); queue, store and captioner are swapped for in-memory fakes |
| Smoke | `tests/smoketests/` | running API (pass `--api-url` to override) |
| UI | `tests/uitests/` | headless Chrome + Selenium; starts the real `ui` server itself |
| System | `tests/systemtests/` | Docker Compose |

### Where a test lives

The unit and integration tests mirror the package layout, so a test sits where the code it covers sits, and the
added layers are as visible in the tests as in the source:

```
tests/unittests/  (and tests/integrationtests/)
├── read/               scene loaders, image stores          ← backseat_driver/read/
│   └── s3/             bucket store, stored loader          ← backseat_driver/read/s3/
├── process/            captioners and their backends        ← backseat_driver/process/
├── write/              JSON writer                          ← backseat_driver/write/
│   └── job_store/      job database: tables, queries        ← backseat_driver/write/job_store/
├── transport/          queues, workers, the API job client  ← backseat_driver/transport/
│   └── job_store/      job store: results + job state       ← backseat_driver/transport/job_store/
├── show/               report, metrics, report UI           ← backseat_driver/show/
├── api/                routes, dependencies, handlers       ← backseat_driver/api/
├── cli/                commands                             ← backseat_driver/cli/
└── test_pipeline.py, test_stacks.py, test_layering.py ...   ← the core and cross-cutting checks
```

Tests for something that spans packages (the pipeline, the wiring in `stacks.py`, the import rules in
`test_layering.py`, config, models) stay at the top of their layer. Fakes and fixtures shared by several folders
live in `tests/fakes.py` and the layer's `conftest.py`.

### Unit tests

```bash
uv run pytest tests/unittests -v
```

No I/O, no network, no GPU. `process/backends/huggingface.py` imports transformers lazily inside its default factory, which the backend takes as a constructor argument so these tests can pass a fake — see `tests/unittests/process/backends/test_huggingface.py`. The scene loader takes its table reader the same way (`tests/unittests/read/dataset/test_nuscenes_scene_loader.py`).

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

Coverage is measured over the whole `backseat_driver` package.

### Benchmarks

```bash
just bench   # or: uv run pytest tests/benchmarks --codspeed
```

`tests/benchmarks/` holds [pytest-codspeed](https://codspeed.io/docs/reference/pytest-codspeed) benchmarks
for the pipeline (by batch size), the queue workers, queue-message (de)serialization, the JSON writer, nuScenes
keyframe selection and table reads, and the backends' per-image work (decoding, request building). Like the unit tests they run against in-memory fakes, so they measure the code around the VLM, not
the model. What the ingest worker imports is guarded by `tests/integrationtests/transport/test_import_cost.py`, since
it is paid per message. The `CodSpeed` workflow runs them in CPU simulation mode on every push and pull request and reports
regressions on the PR. To measure locally the same way, install the [CodSpeed CLI](https://codspeed.io/docs/cli)
and run `codspeed run --mode simulation -- uv run pytest tests/benchmarks --codspeed`.

## Package structure

```
backseat_driver/
├── api/            # FastAPI service (/describe, /jobs, /images, /health, /ready)
│   └── routers/
├── pipeline.py     # ScenePipeline + describe_keyframe: read -> process, the spine (`describe` adds write)
├── read/           # 1. read: SceneLoader + nuScenes loader, ImageStore + local store
│   └── s3/         #    (added) the dataset in a bucket: needed once workers run on other machines
├── process/        # 2. process: Captioner port, CaptionBackend (HuggingFace/Ollama/Anthropic) + CaptionModel
├── write/          # 3. write: JSON writer
│   └── job_store/  #    (added) the job database's tables and queries: what actually writes
├── transport/      # (added) the seam between read and process: JobQueue, in-process + Celery queues, ingest/caption workers
│   └── job_store/  #    JobStore port and its SQL adapter: results from many workers and the job record that says when they are all in
├── show/           # separate role: report and UI over what was written
├── errors.py       # BackseatDriverError hierarchy
├── cli/            # Typer CLI — describe, report, worker, db, dataset, test smoke
├── models/         # Shared domain models (pure Pydantic)
├── config.py       # Settings (pydantic-settings, env-var backed)
└── logger.py       # Loguru setup; LogFormat enum
tests/
├── unittests/          mirrors backseat_driver/: read/, process/, write/, transport/, show/, api/, cli/
├── integrationtests/   the same folders, with real units wired together
├── smoketests/
├── uitests/
└── systemtests/
```

## Extending the pipeline

### Swapping the VLM

`process/captioner.py` defines a `Captioner` abstract class (`caption(image_path) -> str`, `healthcheck() -> bool`).
Subclass it in `backseat_driver/process/`, next to the existing backends (e.g. a different HF model, or a call to an external VLM API) and pass it
into `ScenePipeline` — nothing else needs to change.

### Adding an API endpoint

1. Add request/response models to `backseat_driver/models/` or directly in the router module.
2. Add domain logic to the matching capability package (`read/`, `process/`, `write/`, `transport/`).
3. Create or extend a router in `backseat_driver/api/routers/`.
4. Register the router in `backseat_driver/api/app.py`.
5. Add integration tests in `tests/integrationtests/`.

## Docker

```bash
just docker-run          # run the pipeline in the cli container
just up                  # API + RabbitMQ + Postgres + workers
just test-system        # system tests
```

Images are defined in `docker/Dockerfile` with one build target per service: `cli`, `api`, `ingest-worker` and `caption-worker`. See [Running it](running.md) for how every way of running the project fits together.

## Pre-commit hooks

```bash
uv run pre-commit install          # register
uv run pre-commit run --all-files  # run manually (= just check)
```

Hooks run ruff and ty on every commit. The CI workflow also runs `pip-audit` to check for known
security vulnerabilities in dependencies.
