# Development Guide

## Prerequisites

| Tool | Install | Purpose |
|---|---|---|
| [Python 3.13+](https://www.python.org/) | system / pyenv | Runtime |
| [uv](https://docs.astral.sh/uv/) | `curl -LsSf https://astral.sh/uv/install.sh \| sh` | Package manager |
| [just](https://github.com/casey/just) | `cargo install just` / `brew install just` | Task runner |
| [Docker](https://www.docker.com/) | platform installer | Compose system tests |

## Setup

```bash
git clone <repo-url>
cd vlm_scene_description
uv sync --group dev         # install all deps + dev tools
uv run pre-commit install   # register git hooks
cp .env.example .env
```

## Available tasks

Run `just --list` at any time to see all targets. The full table:

| Command | Description |
|---|---|
| `just dev` | Dev server with hot reload (`fastapi dev`) |
| `just serve` | Production-mode server (`fastapi run`, binds `0.0.0.0:8080`) |
| `just migrate` | Apply all pending database migrations (`alembic upgrade head`) |
| `just migrate-rev "msg"` | Generate a migration from ORM model changes |
| `just migrate-down` | Roll back the last migration |
| `just test` | Unit + integration tests with coverage |
| `just test-smoke` | Smoke tests against a running service |
| `just test-system` | System tests (requires the service to be running locally) |
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
just typecheck  # mypy strict
just check      # pre-commit on all files (ruff + mypy)
```

All three are enforced in CI.

## Tests

There are four test layers, from fastest to slowest:

| Layer | Path | Infrastructure |
|---|---|---|
| Unit | `tests/unittests/` | none |
| Integration | `tests/integrationtests/` | in-process (no external services) |
| Smoke | `tests/smoketests/` | running API (set `API_URL` to override) |
| System | `tests/systemtests/` | Docker Compose |

### Unit tests

```bash
uv run pytest tests/unittests -v
```

No I/O, no network. Cover pure functions, config parsing, and anything that doesn't need a running service.

### Integration tests

```bash
just test   # unit + integration with coverage
# or
uv run pytest tests/integrationtests -v
```

FastAPI runs in-process via `httpx.ASGITransport` — no port binding, no subprocess. Fast and fully isolated.

```python
# Pattern used in tests/integrationtests/conftest.py
transport = httpx.ASGITransport(app=app)
async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
    ...
```

### Smoke tests

```bash
just test-smoke              # against http://127.0.0.1:8080 (default)
API_URL=http://staging:8080 just test-smoke   # against another target
```

Or via the CLI:

```bash
uv run vlm_scene_description test smoke --api-url http://staging:8080
```

Tests skip automatically when the target is not reachable.

### System tests (Docker Compose)

```bash
just test-compose
```

Builds all images, starts the full stack, runs `tests/systemtests/` and `tests/smoketests/` inside the `systemtest` container, then tears everything down. The `systemtest` service has `profiles: [test]` so it doesn't start with a plain `docker compose up`.

To run system tests against an already-running stack:

```bash
API_URL=http://my-server:8080 uv run pytest tests/systemtests -v
```

### Coverage

```bash
just test   # includes --cov; must stay above 80% (enforced in CI)
```

Coverage is measured over `vlm_scene_description` excluding `cli/`.

## Package structure

```
vlm_scene_description/
├── api/            # FastAPI app, routes, lifespan, exception handlers
│   └── routers/    # One router per domain area
├── bl/             # Business logic layer
├── cli/            # Typer CLI entry-point and subcommands
├── db/             # Repository ABC + MemoryRepository + SQLiteRepository
├── models/         # Shared domain models (pure Pydantic)
├── config.py       # Settings (pydantic-settings, env-var backed)
└── logger.py       # Loguru setup; LogFormat enum
tests/
├── unittests/
├── integrationtests/
├── smoketests/
└── systemtests/
```

## Extending the service

### Adding an API endpoint

1. Add request/response models to `vlm_scene_description/models.py` (or a new `api/models.py`).
2. Add business logic to `vlm_scene_description/bl/`.
3. Create or extend a router in `vlm_scene_description/api/routers/`.
4. Register the router in `vlm_scene_description/api/app.py`.
5. Add integration tests in `tests/integrationtests/`.

### Adding a repository method

1. Declare the abstract method in `vlm_scene_description/db/base.py`.
2. Implement it in `db/memory.py` (and `db/sqlite.py` if it exists).
3. Keep the factory in `db/factory.py` up to date.

### Adding or changing a database table

1. Define/modify the ORM table in `vlm_scene_description/db/orm.py` as a subclass of `Base`.
2. Generate the migration: `just migrate-rev "add users table"`.
3. Review the generated file under `migrations/versions/`, then apply with `just migrate`.

Migrations target `Settings.database_url` (the same DB the app uses), so no duplicate config.

## Docker

```bash
docker compose up                        # full stack
docker compose up --build                # rebuild images first
docker compose --profile test up         # include systemtest container
```

Images are defined in `docker/Dockerfile` with named build targets: `api`.

## Pre-commit hooks

```bash
uv run pre-commit install          # register
uv run pre-commit run --all-files  # run manually (= just check)
```

Hooks run ruff and mypy on every commit. The CI workflow also runs `pip-audit` to check for known security vulnerabilities in dependencies.
