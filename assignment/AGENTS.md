# AGENTS.md

## VLM Scene Description — AI Agent Guide

This document provides essential knowledge for AI coding agents (Claude Code, Copilot, Cursor, etc.) to be productive in this codebase. Read this before exploring source files.

---

### 1. Project Architecture & Documentation

**Mandatory reading for architecture:**
- **[docs/index.md](docs/index.md)** — Quick-start and documentation hub.
- **[docs/api.md](docs/api.md)** — Auto-generated API reference for `vlm_scene_description.*`.

The MkDocs docs live in `docs/` and are published to GitHub Pages. Build locally with `just docs`.

**Repository map:**
- `vlm_scene_description/models/` — Pure Pydantic domain models. No imports from any other layer.
- `vlm_scene_description/bl/` — Business logic. Imports `models`. Accepts `db.base.Repository` via constructor injection. No FastAPI types, no HTTP concepts.
- `vlm_scene_description/bl/http_client.py` — Example pattern for outbound HTTP calls using `httpx`. Copy and adapt; test with `respx`.

- `vlm_scene_description/api/` — FastAPI application, routes, and lifespan setup.
- `vlm_scene_description/api/middleware.py` — `RequestIDMiddleware`: injects `X-Request-ID` into every request and binds it to all log lines via `logger.contextualize(request_id=...)`.

- `vlm_scene_description/db/` — `Repository` ABC + `MemoryRepository` + `factory.py`.

- `vlm_scene_description/config.py` — Pydantic-settings `Settings` class; all configuration comes from environment variables prefixed with `VLM_SCENE_DESCRIPTION_`.
- `vlm_scene_description/logger.py` — Loguru setup; call `setup_logging()` once per process entry-point.
- `tests/unittests/` — Fast, isolated unit tests (no I/O).
- `tests/integrationtests/` — In-process tests using `httpx.AsyncClient` with `ASGITransport`.
- `tests/smoketests/` — Black-box HTTP tests against a running service.
- `tests/systemtests/` — Full Docker Compose end-to-end tests.

---

### 2. Developer Workflows

- **Dependency management**: Always use `uv`. Never invoke `python` directly — use `uv run <command>`.
- **Discover available tasks**: `just --list`

**Key commands:**

| Command | Purpose |
|---|---|
| `just dev` | Dev server with hot reload (`fastapi dev`) |
| `just test` | Unit + integration tests with coverage |
| `just lint` | Ruff check + format check (CI mode, no fixes) |
| `just fmt` | Auto-fix and reformat |
| `just typecheck` | ty type check |
| `just test-compose` | Full system test via Docker Compose |
| `just observability` | App + OTel Collector + Tempo + Prometheus + Grafana (http://localhost:3000) |
| `just test-smoke` | Smoke tests against a running service |
| `just docs` | Build HTML docs with MkDocs |

**CLI entry-point:** `uv run vlm_scene_description --help`

---

### 3. Configuration

- All settings live in `vlm_scene_description/config.py` — the `Settings` class backed by pydantic-settings.
- Every environment variable is prefixed with `VLM_SCENE_DESCRIPTION_` (e.g., `VLM_SCENE_DESCRIPTION_API_PORT=9090`).
- Override locally via `.env` (gitignored). Copy `.env.example` to get started.
- `get_settings()` is `@lru_cache`-decorated — call `get_settings.cache_clear()` in tests that override env vars via `monkeypatch.setenv`.

---

### 4. Testing Conventions

- **Scope constraint**: Only test and lint files you actually modified. Do not run a full-suite ruff or mypy pass over unmodified files.
- **Test layers** (fastest → slowest):
  1. `tests/unittests/` — pure logic, no network, no filesystem.
  2. `tests/integrationtests/` — in-process FastAPI via `httpx.ASGITransport`.
  3. `tests/smoketests/` — live HTTP; requires a running service (set `API_URL` to override target).
  4. `tests/systemtests/` — Docker Compose, runs everything containerised.
- **AAA structure**: Every test must follow Arrange → Act → Assert with a blank line between each phase. Name the sections with a comment only when the block is non-obvious; otherwise the blank lines are enough.
  ```python
  def test_something():
      client = build_client(api_url="http://test")   # Arrange

      response = client.get("/health")               # Act

      assert response.status_code == HTTPStatus.OK   # Assert
  ```
- **HTTP status codes**: Always use `from http import HTTPStatus` and reference constants by name (`HTTPStatus.OK`, `HTTPStatus.NOT_FOUND`, `HTTPStatus.UNPROCESSABLE_ENTITY`). Never use bare integer literals (`200`, `404`) for status code assertions.
- **Async tests**: `asyncio_mode = "auto"` in `pyproject.toml` — no `@pytest.mark.asyncio` decorator needed.
- **httpx**: Always use `httpx.ASGITransport(app=app)` in integration tests (the deprecated `app=` kwarg is not supported in recent versions).

---

### 5. Code Conventions

- **Fail fast**: Never swallow exceptions or add silent fallbacks that alter behaviour. Raise an explicit `ValueError` or `RuntimeError` when invariants are violated — bugs caught immediately are far easier to debug than silent failures discovered later.
- **No speculative abstraction**: Don't add feature flags, backwards-compat shims, or conditional paths for hypothetical future requirements. Three similar lines is better than a premature abstraction.
- **Loguru**: Call `setup_logging()` once per process entry-point (API lifespan, worker `main()`, CLI commands that produce output). Import `from loguru import logger` everywhere else — do not use `logging.getLogger`. Use `logger.bind(key=value).info(...)` for one-shot structured fields; use `logger.contextualize(key=value)` (async context manager) for request-scoped fields.
- **Database schema**: Never change a table's shape without a migration. Edit the ORM model in `db/orm.py`, then `just migrate-rev "msg"` and review the generated file before committing. Do not hand-write SQL DDL in application code.
- **hypothesis**: Use for property-based tests on pure functions — especially config parsing, model validation, and bl/ business logic. Import `from hypothesis import given, strategies as st`. See `tests/unittests/test_config.py` for examples.
- **respx**: Use to mock outbound `httpx` calls in unit tests. Decorate with `@respx.mock` or use as a context manager. See `tests/unittests/test_http_client.py` for the pattern. Never use respx in integration tests — those run the full in-process stack.
- **schemathesis**: Automatically fuzzes all OpenAPI operations declared in the schema. Tests live in `tests/integrationtests/test_schema.py`. Run with `just test` — it's part of the normal integration test suite.
- **Comments**: Comment the *why*, not the *what*. Delete any comment that merely restates what the code already says.
- **Scratch files**: Place any temporary debug or exploration scripts under `scratch/` (gitignored). Do not leave them in the project root or any package directory.

---

### 6. Documentation (`docs/`)

- Write or update files in `docs/` for permanent architecture overviews, design decisions, and subsystem explanations.
- Do **not** put agent behaviour rules here (they belong in this file) or temporary scratch notes.
- When adding a new doc page, add it to the `nav:` section in `mkdocs.yml` and link it from `docs/index.md`.
- Format: Markdown. Use LaTeX inside Markdown only for non-trivial math.

---

*Keep this file up-to-date as the project evolves. Architecture details go in `docs/`; agent behavioural rules go here.*
