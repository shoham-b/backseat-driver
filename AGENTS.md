# AGENTS.md

## Backseat Driver — AI Agent Guide

This document provides essential knowledge for AI coding agents (Claude Code, Copilot, Cursor, etc.) to be productive in this codebase. Read this before exploring source files.

---

### 1. Project Architecture & Documentation

**Mandatory reading for architecture:**
- **[docs/index.md](docs/index.md)** — Quick-start and documentation hub.
- **[docs/api.md](docs/api.md)** — Auto-generated API reference for `backseat_driver.*`.

The MkDocs docs live in `docs/` and are published to GitHub Pages. Build locally with `just docs`.

**Repository map:**
- `backseat_driver/models/` — Pure Pydantic domain models, one module per subject: `scene.py` (`SceneKeyframe`, `SceneDescription` extends it), `job.py` (`JobReference` base for `job_id`/`transaction_id`, `Job`, `JobState`), `tasks.py` (`IngestTask`, `CaptionTask`, queue messages). `__init__.py` only re-exports. No imports from any other layer.
- `backseat_driver/captioning/`, `scenes/`, `jobs/` — Capability packages. Each holds an abstract class (ABC "port") **and** its platform implementations side by side; orchestration code in the same package depends only on the ports, so it is testable with fakes and never imports nuscenes-devkit/transformers/celery/psycopg. New external integrations go in the matching package, next to the port they implement. Adapters never connect in their constructors.
  - `captioning/` — `captioner.py` (`Captioner` ABC); `backend.py` (`CaptionBackend` ABC: the runtime, i.e. where inference happens) and `model.py` (`CaptionModel`: which model runs and its prompt) are separate; `backend_captioner.py` (`BackendCaptioner`) pairs one of each behind `Captioner`. Backends: `huggingface_backend.py` wraps a HuggingFace `image-to-text` pipeline (one per model, loaded lazily on first use); `ollama_backend.py` and `anthropic_backend.py` call a local Ollama server / the hosted Claude API over the `HttpClient` port (`http_client.py`, stdlib `UrllibHttpClient` adapter) for verbose, prompt-driven descriptions. `factory.py` (`build_backend`, `build_captioner`) picks the backend from `BACKSEAT_DRIVER_VLM_BACKEND` and the model from config.
  - `scenes/` — `nuscenes_dataset.py` (downloads/validates the local nuScenes copy), `scene_loader.py` (`SceneLoader` ABC), `nuscenes_scene_loader.py` (nuScenes devkit), `pipeline.py` (`ScenePipeline`, orchestrates loader → captioner → `list[SceneDescription]`; never imports nuscenes-devkit/transformers/torch directly), `writer.py` (writes `list[SceneDescription]` as JSON).
  - `jobs/` — `/jobs` processing, in two run modes chosen by `BACKSEAT_DRIVER_MODE` via `factory.py` (`build_job_backend`): `monolith` (default; `in_process_job_queue.py` + `sql_job_store.py` over a SQLite file (`BACKSEAT_DRIVER_JOBS_DB_PATH`; `in_memory_job_store.py` when empty) run the workers on a thread inside the API process, so `just dev` needs no broker, Postgres or workers) or `distributed` (docker compose; Celery + Postgres with `ingest-worker`/`caption-worker` built from their own Dockerfile targets). Distributed parts: `job_queue.py` (`JobQueue` ABC) + `celery_job_queue.py` (Celery/RabbitMQ); `job_store.py` (`JobStore` ABC) + `sql_job_store.py` (maps rows to domain models) over `orm.py` (SQLAlchemy tables) and `storage.py` (`JobStorage`: engine/sessions/queries, returns rows not domain models; only `sql_job_store.py` uses it); `workers.py` (`IngestWorker`/`CaptionWorker` handlers that reuse `describe_keyframe`). `backseat_driver/tasks.py` wraps the handlers as Celery tasks (`register_tasks`), with the lazily built workers held by `Workers`. See `docs/distributed.md`.
- `backseat_driver/reporting/` — Model-comparison report behind `report`/`ui`: `metrics.py` (content-word precision/recall/F1 against the nuScenes label), `report.py` (groups `SceneDescription`s by scene and camera, scores them), `html_report_writer.py` + `report_template.html` (one self-contained HTML page, images inlined). Pure logic plus file I/O; no platform dependencies.
- `backseat_driver/errors.py` — `DomainError` hierarchy shared by all packages; `api/exception_handlers.py` maps these to HTTP status codes.

- `backseat_driver/cli/` — Typer CLI. `run` is the primary command: runs the full pipeline over a local nuScenes dataset and writes JSON to `output/<backend>__<model>.json` (inferred via `Settings.output_path_for`). `report` / `ui` build or serve the HTML comparison of those files. `test smoke` runs the smoke suite against a running API. Commands (like API routes) are thin entrypoints with no logic of their own: they build the real collaborators and call the classes below, so unit tests inject fakes there (`tests/fakes.py`, `Settings(...)` kwargs) and only the integration tests drive the commands, with env vars for the CLI process (`runner.invoke(..., env=...)`), a `file://` dataset archive and a stub model server. Prefer fakes subclassing the ports over `monkeypatch`/`mock.patch`.

- `backseat_driver/api/` — Optional deployment mode: a small FastAPI service exposing the same `Captioner` as a `/describe` endpoint for single-image, on-demand captioning (see `docs/architecture.md` for when to use this vs. the CLI).
- `backseat_driver/api/middleware.py` — `RequestIDMiddleware`: injects `X-Request-ID` into every request and binds it to all log lines via `logger.contextualize(request_id=...)`.
- `backseat_driver/api/routers/jobs.py` — `POST /jobs` (202), `GET /jobs` (newest first, `state`/`limit`), `GET /jobs/{id}`, `GET /jobs/{id}/descriptions`.
- CLI: `worker ingest|caption` (Celery workers) and `db init` (creates tables).

- `deploy/` — `k8s/` is the kustomize base (plus `examples/`); `components/keda-autoscaling/` adds queue-depth autoscaling of the workers (needs KEDA); `kind/` is the local-cluster overlay (`just k8s-up` / `k8s-down`). See `docs/deployment.md`.

- `backseat_driver/config.py` — Pydantic-settings `Settings` class; all configuration comes from environment variables prefixed with `BACKSEAT_DRIVER_`.
- `backseat_driver/logger.py` — Loguru setup; call `setup_logging()` once per process entry-point.
- `tests/unittests/` — Fast, isolated unit tests (no I/O), one function or method under test at a time.
- `tests/integrationtests/` — In-process tests using `httpx.AsyncClient` with `ASGITransport`, plus in-process worker tests.
- `tests/smoketests/` — Black-box HTTP tests against a running service.
- `tests/systemtests/` — Full Docker Compose end-to-end tests.
- `tests/uitests/` — Selenium tests that drive the model-comparison UI (the real `ui` server) in headless Chrome. Run with `just test-ui`; set `CHROME_BIN`/`CHROMEDRIVER` to use a specific browser.

---

### 2. Developer Workflows

- **Dependency management**: Always use `uv`. Never invoke `python` directly — use `uv run <command>`.
- **Discover available tasks**: `just --list`

**Key commands:**

| Command | Purpose |
|---|---|
| `just run` | Run the scene-description pipeline (the primary deliverable) |
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
- **Test layers** (fastest → slowest):
  1. `tests/unittests/` — pure logic, no network, no filesystem. Each test exercises a single unit (one function or method) in isolation; replace its collaborators with fakes or stubs instead of running them. A test that drives several real units together belongs in `tests/integrationtests/`.
  2. `tests/integrationtests/` — in-process FastAPI via `httpx.ASGITransport`, and the `jobs/` workers (`IngestWorker`/`CaptionWorker`) run in-process the same way: real worker, queue and store wired together, with only the platform edges (Celery/RabbitMQ, Postgres, models) swapped for in-memory implementations.
  3. `tests/smoketests/` — live HTTP; requires a running service (pass `--api-url` to override the target).
  4. `tests/uitests/` — Selenium + headless Chrome against the real `ui` server.
  5. `tests/systemtests/` — Docker Compose, runs everything containerised.
- **Unit test logic, keep adapters thin**: Put decisions and transformations in plain classes/functions behind the ports and unit test those. Adapters (FastAPI routes, Postgres/SQLAlchemy, Celery, HTTP clients) only translate and delegate, so they are covered by integration/smoke/system tests, not unit tests. Don't hand-mock a framework or database with `mock.patch`, but when a purpose-built fake exists and is cheap (a Postgres test library, an in-memory engine), using it to test an adapter is fine. Don't chase 100% coverage: `fail_under` is 95 and the gap is expected to be adapter glue. If an adapter needs a test to feel safe, move the logic out of it instead.
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
- **hypothesis**: Use for property-based tests on pure functions — especially config parsing, model validation, and domain logic in `scenes/`/`jobs/`. Import `from hypothesis import given, strategies as st`. See `tests/unittests/test_config.py` for examples.
- **Heavy deps (transformers/torch/nuscenes-devkit) stay behind lazy imports and injected factories**: `captioning/huggingface_backend.py` (`transformers_pipeline`) and `scenes/nuscenes_scene_loader.py` (`open_nuscenes`) import them inside the default factory, not at module scope, and take the factory as a constructor argument, so unit tests hand in a fake without a model download or a dataset on disk. See `tests/unittests/test_huggingface_backend.py` and `test_nuscenes_scene_loader.py`.
- **No monkeypatch / mock.patch in tests**: inject collaborators through constructors or arguments (`HttpClient`, engine factory, Celery app builder, `Workers`, `create_app(settings)` + `dependency_overrides`) and use hand-written fakes subclassing the ABC ports in `tests/fakes.py`, so a port change breaks the fake.
- **schemathesis**: Automatically fuzzes all OpenAPI operations declared in the schema. Tests live in `tests/integrationtests/test_schema.py`. Run with `just test` — it's part of the normal integration test suite.
- **Comments**: Only write a comment that tells the reader something new: the *why*, a constraint, or a non-obvious consequence. Never describe what the code plainly does, and delete any existing comment that merely restates it.
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
