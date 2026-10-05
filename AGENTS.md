# AGENTS.md

## Backseat Driver — AI Agent Guide

This document provides essential knowledge for AI coding agents (Claude Code, Copilot, Cursor, etc.) to be productive in this codebase. Read this before exploring source files.

---

### 1. Project Architecture & Documentation

**Mandatory reading for architecture:**
- **[docs/index.md](docs/index.md)** — Quick-start and documentation hub.
- **[docs/api.md](docs/api.md)** — Auto-generated API reference for `backseat_driver.*`.

The MkDocs docs live in `docs/` and are published to GitHub Pages. Build locally with `just docs`.

**Repository map:** each package's modules carry their own docstrings; read those for the detail. What matters across packages:
- **The shape: read → process → write.** `pipeline.py` runs the three stages in order and `describe` is that, in one process. Scaling out adds a queue between read and process, the job store the queue forces, and what crossing machines forces (the bucket); see `docs/ladder.md` before changing how the layers relate.
- **The core** (`models/`, `read/`, `process/`, `write/`, `pipeline.py`) is complete on its own and must never import **the added layers** (`transport/`, `read/s3/`, `write/job_store/`) or Celery/aioboto3/SQLAlchemy/psycopg; `tests/unittests/test_layering.py` enforces it. Each package holds an abstract class (ABC "port") **and** its platform implementations side by side; orchestration code depends only on the ports, so it is testable with fakes and never imports nuscenes-devkit/transformers/celery/psycopg. New external integrations go in the matching package, next to the port they implement. Adapters never connect in their constructors. The ports are deliberately separate: no shared base class.
- `stacks.py` is the one place the wiring is read (a recipe per rung). Recipes only build collaborators; they never connect.
- `SceneKeyframe.image_path` is always the dataset-relative key; only an `ImageStore` turns a key into bytes.
- `models/` is pure Pydantic and imports from no other layer. `errors.py` holds the `DomainError` hierarchy; `api/exception_handlers.py` maps it to HTTP status codes.
- CLI commands and API routes are thin entrypoints with no logic of their own: they build the real collaborators and call the classes behind them, so unit tests inject fakes there (`tests/fakes.py`, `Settings(...)` kwargs) and only the integration tests drive the commands. Prefer fakes subclassing the ports over `monkeypatch`/`mock.patch`.
- **API routes are `async def`** and await the captioner, the image service, the job store and the queue, which move any blocking work of their own to `asyncio.to_thread` (the Celery producer does). Never put a blocking call directly in a route; if one appears, wrap that one call in `asyncio.to_thread`, not `run_in_threadpool`.
- `config.py` is the pydantic-settings `Settings`; every variable is prefixed `BACKSEAT_DRIVER_`. `logger.py` sets up Loguru; call `setup_logging()` once per process entry-point.
- Tests live in `tests/` (layers in section 4); `deploy/` holds the Kubernetes manifests.

---

### 2. Developer Workflows

- **Dependency management**: Always use `uv`. Never invoke `python` directly — use `uv run <command>`.
- **Discover available tasks**: `just --list`

**Key commands:**

| Command | Purpose |
|---|---|
| `just describe` | Run the scene-description pipeline (the primary deliverable) |
| `just dev` | Optional API dev server with hot reload (`fastapi dev`), monolith mode: no infra needed |
| `just dev-distributed` | Same against RabbitMQ + Postgres in Docker (`just infra`), distributed mode |
| `just test` | Unit + integration tests with coverage |
| `just lint` | Ruff check + format check (CI mode, no fixes) |
| `just fmt` | Auto-fix and reformat |
| `just typecheck` | ty type check |
| `just test-system` | Full system test via Docker Compose |
| `just test-smoke` | Smoke tests against a running service |
| `just docs` | Build HTML docs with MkDocs |

**CLI entry-point:** `uv run backseat-driver --help`

---

### 3. Configuration

- All settings live in `backseat_driver/config.py` — the `Settings` class backed by pydantic-settings.
- Every environment variable is prefixed with `BACKSEAT_DRIVER_` (e.g., `BACKSEAT_DRIVER_API_PORT=9090`).
- Override locally via `.env` (gitignored). Copy `.env.example` to get started.
- Build `Settings(_env_file=None, ...)` (or `make_settings(...)` from `tests/fakes.py`) with keyword arguments in tests rather than setting environment variables; `get_settings()` is `@lru_cache`-decorated, so tests should not go through it.

---

### 4. Testing Conventions

- **Scope constraint**: Only test and lint files you actually modified. Do not run a full-suite ruff or mypy pass over unmodified files.
- **Layout**: `tests/unittests/` and `tests/integrationtests/` mirror the package layout (`read/` with `read/dataset/`, `read/images/` and `read/s3/`, `process/`, `write/` with `write/job_store/`, `transport/` with `transport/job_store/`, `show/`, `api/`, `cli/`), so a test sits where the code it covers sits. Tests of something that spans packages (`test_pipeline.py`, `test_stacks.py`, `test_layering.py`, config, models) stay at the top of the layer. Put a new test in the folder of the package it covers, and add an `__init__.py` to any new folder.
- **Test layers** (fastest → slowest):
  1. `tests/unittests/` — pure logic, no network, no filesystem. Each test exercises a single unit (one function or method) in isolation; replace its collaborators with fakes or stubs instead of running them. A test that drives several real units together belongs in `tests/integrationtests/`.
  2. `tests/integrationtests/` — in-process FastAPI via `httpx.ASGITransport`, and the `transport/` workers (`IngestWorker`/`CaptionWorker`) run in-process the same way: real worker, queue and store wired together, with only the platform edges (Celery/RabbitMQ, Postgres, models) swapped for in-memory implementations.
  3. `tests/smoketests/` — live HTTP; requires a running service (pass `--api-url` to override the target).
  4. `tests/uitests/` — Selenium + headless Chrome against the real UI server.
  5. `tests/systemtests/` — Docker Compose, runs everything containerised.
- **Unit test logic, keep adapters thin**: Put decisions and transformations in plain classes/functions behind the ports and unit test those. Adapters (FastAPI routes, Postgres/SQLAlchemy, Celery, HTTP clients) only translate and delegate, so they are covered by integration/smoke/system tests, not unit tests. Don't hand-mock a framework or database with `mock.patch`, but when a purpose-built fake exists and is cheap (a Postgres test library, an in-memory engine), using it to test an adapter is fine. Don't chase 100% coverage: `fail_under` is 90 and the gap is expected to be adapter glue. A test that only exists to move the number (asserting a trivial path, or needing a mock) is worse than the uncovered line. If an adapter needs a test to feel safe, move the logic out of it instead.
- **AAA structure**: Every test must follow Arrange → Act → Assert with a blank line between each phase. Name the sections with a comment only when the block is non-obvious; otherwise the blank lines are enough.
  ```python
  def test_something():
      client = build_client(api_url="http://test")  # Arrange

      response = client.get("/health")  # Act

      assert response.status_code == HTTPStatus.OK  # Assert
  ```
- **HTTP status codes**: Always use `from http import HTTPStatus` and reference constants by name (`HTTPStatus.OK`, `HTTPStatus.NOT_FOUND`, `HTTPStatus.UNPROCESSABLE_ENTITY`). Never use bare integer literals (`200`, `404`) for status code assertions.
- **Async tests**: `asyncio_mode = "auto"` in `pyproject.toml` — no `@pytest.mark.asyncio` decorator needed.
- **httpx**: Always use `httpx.ASGITransport(app=app)` in integration tests (the deprecated `app=` kwarg is not supported in recent versions).

---

### 5. Code Conventions

- **Fail fast**: Never swallow exceptions or add silent fallbacks that alter behaviour. Raise an explicit `ValueError` or `RuntimeError` when invariants are violated — bugs caught immediately are far easier to debug than silent failures discovered later.
- **No speculative abstraction**: Don't add feature flags, backwards-compat shims, or conditional paths for hypothetical future requirements. Three similar lines is better than a premature abstraction.
- **Loguru**: Call `setup_logging()` once per process entry-point (API lifespan, CLI commands that produce output). Import `from loguru import logger` everywhere else — do not use `logging.getLogger`. Use `logger.bind(key=value).info(...)` for one-shot structured fields; use `logger.contextualize(key=value)` (async context manager) for request-scoped fields.
- **hypothesis**: Use for property-based tests on pure functions — especially config parsing, model validation, and domain logic in `read/`/`transport/`. Import `from hypothesis import given, strategies as st`. See `tests/unittests/test_config.py` for examples.
- **Heavy deps (transformers/torch) stay behind lazy imports and injected factories**: `process/backends/huggingface.py` (`transformers_pipeline`) imports them inside the default factory, not at module scope, and takes the factory as a constructor argument, so unit tests hand in a fake without a model download. `read/dataset/nuscenes_scene_loader.py` likewise takes its table reader (`open_nuscenes`, which returns `NuScenesTables`) as an argument. **Do not import nuscenes-devkit, matplotlib, scikit-learn or scipy on the ingest path**: ingest runs once per message and pays for every import; `tests/integrationtests/transport/test_import_cost.py` fails if they come back. See `tests/unittests/process/backends/test_huggingface.py` and `test_nuscenes_scene_loader.py`.
- **The core is async end to end.** `Captioner`, `CaptionBackend`, `SceneLoader`, `ImageStore.local_copy`, `DatasetStore`, `JobStore` and `JobQueue` are coroutines, as are `ScenePipeline.run`, `describe_keyframe(s)` and the worker handlers. The API's event loop is the one loop: the in-process queue is a consumer task on it and the SQLite store's connections belong to it. The sync edges that remain (a Celery task, `describe`, `db init`, `dataset upload`, the report's image source) each run their coroutine with one `asyncio.run`, or, in a Celery worker, on the process's own long-lived loop (`worker_loop`), and nothing below an edge starts one. A connection belongs to the loop that opened it, so a worker process keeps one loop for its whole life (`worker_loop`) and the S3 store opens a client per operation. Code that blocks (local inference) moves to `asyncio.to_thread`, file reads and writes use `anyio.Path`; code that waits on the network awaits it (`HttpClient.post_json_async`, `is_reachable_async`, backed by httpx; the S3 store, backed by aioboto3, which opens a client per operation because a client belongs to one event loop). Bound a call with `asyncio.timeout` in the caller: an async function takes no `timeout` parameter (ruff ASYNC109). Tests of async code are `async def`, except under hypothesis, which cannot drive a coroutine (use `asyncio.run` there).
- **No monkeypatch / mock.patch in tests**: inject collaborators through constructors or arguments (`HttpClient`, engine factory, Celery app builder, `Workers`, `create_app(settings)` + `dependency_overrides`) and use hand-written fakes subclassing the ABC ports in `tests/fakes.py`, so a port change breaks the fake.
- **schemathesis**: Automatically fuzzes all OpenAPI operations declared in the schema. Tests live in `tests/integrationtests/api/test_schema.py`. Run with `just test` — it's part of the normal integration test suite.
- **File layout**: one module per class or tightly coupled group, named for what it holds. An ABC port, each platform implementation of it, and pure helpers get separate modules, and imports only point down the layers (`models/` imports nothing; adapters import ports, never the reverse). Split a file when it mixes layers (SQL with decisions, HTTP bodies with routes), not to make it shorter.
- **Comments**: Only write a comment that tells the reader something new: the *why*, a constraint, or a non-obvious consequence. Never describe what the code plainly does, and delete any existing comment that merely restates it. Never name a file or module path in a comment (it goes stale silently when the file moves); say what the thing is, or point at a doc page by title. The exception is a command that needs the path to work.
- **PR review comments**: Always reply to every review comment on the PR, even when the reply is just "done" to show you accept it. Reply in the comment's own thread; for a fix, include the commit SHA.
- **Scratch files**: Place any temporary debug or exploration scripts under `scratch/` (gitignored). Do not leave them in the project root or any package directory.

---

### 6. Documentation (`docs/`)

- Write or update files in `docs/` for permanent architecture overviews, design decisions, and subsystem explanations.
- Do **not** put agent behaviour rules here (they belong in this file) or temporary scratch notes.
- When adding a new doc page, add it to the `nav:` section in `mkdocs.yml` and link it from `docs/index.md`.
- Format: Markdown. Use LaTeX inside Markdown only for non-trivial math.

---

*Keep this file up-to-date as the project evolves. Architecture details go in `docs/`; agent behavioural rules go here.*
