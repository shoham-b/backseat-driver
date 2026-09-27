# Architecture

## Components

| Component | Entry point | Default address | Description |
|---|---|---|---|
| **api** | `just dev` (dev) / `just serve` (production) | `:8080` | FastAPI HTTP service |


## Data flow

```
┌─────────────────────────────────────────────┐
│  Client                                      │
│  HTTP request                                │
└────────────────────┬────────────────────────┘
                     │ HTTP
                     ▼
┌─────────────────────────────────────────────┐
│  vlm_scene_description.api  (:8080)            │
│  FastAPI                                     │
│                                              │
│  1. Validate request                         │
│  2. Call service layer                       │
│  3. Return response                          │
└────────────────────┬────────────────────────┘
                     │ Python call
                     ▼
┌─────────────────────────────────────────────┐
│  vlm_scene_description.services                │
│  Business logic — no HTTP, no DB knowledge  │
│                                              │
│  Accepts: models + Repository (injected)    │
│  Returns: domain models                      │
└────────────────────┬────────────────────────┘
                     │ Repository interface
                     ▼
┌─────────────────────────────────────────────┐
│  vlm_scene_description.db                      │
│  MemoryRepository  │  SQLiteRepository       │
│  (dev / tests)     │  (production)           │
└─────────────────────────────────────────────┘
```

## Layer design

```
models/            bl/                    api/
──────────         ───────────            ────
Domain models  →   Business logic    →    FastAPI routes
Pure Pydantic      No HTTP concepts        Request/response
No dependencies    Accepts Repository      Calls bl layer
                   via constructor         Validates input
```

Each layer only imports from layers to its left:

- **`models/`** — pure Pydantic models. No imports from `api/`, `bl/`, or `db/`.
- **`bl/`** — business logic. Imports `models`. Accepts `db.base.Repository` via constructor. No FastAPI types, no HTTP status codes.
- **`db/`** — data access. Implements `Repository` ABC from `db/base.py`. No business logic.
- **`api/`** — HTTP layer. Imports `bl` and `models`. Owns request validation, response serialization, and error mapping.

This separation keeps each layer independently testable: services can be unit-tested with a `MemoryRepository`, and the API can be integration-tested in-process without a real database.

## API contracts

### HTTP API (`vlm_scene_description.api`)

Successes return the documented model directly. Errors use `{"error": {"code": <int>, "status": "<phrase>", "message": "<detail>"}}`.

#### Observability endpoints

| Method | Path | Probe type | k8s field | Description |
|---|---|---|---|---|
| `GET` | `/health` | Liveness | `livenessProbe` | Returns 200 if the process is running — no dependency checks |
| `GET` | `/ready` | Readiness | `readinessProbe` | Returns 200 only when all dependencies (storage, etc.) are reachable; 503 otherwise |
| `GET` | `/metrics` | — | — | Prometheus metrics (scraped by Prometheus/Grafana) |

k8s removes a pod from the load balancer when `/ready` fails, and restarts it when `/health` fails.

> Add your domain endpoints here as the service grows.

## Module responsibilities

| Package | Responsibility |
|---|---|
| [`vlm_scene_description.api`](../vlm_scene_description/api/) | FastAPI app, routes, lifespan, exception handlers |
| [`vlm_scene_description.bl`](../vlm_scene_description/bl/) | Business logic; injected with a `Repository` |
| [`vlm_scene_description.models`](../vlm_scene_description/models.py) | Shared domain models (Pydantic) |
| [`vlm_scene_description.db`](../vlm_scene_description/db/) | `Repository` ABC + `MemoryRepository` + `SQLiteRepository` |
| [`vlm_scene_description.config`](../vlm_scene_description/config.py) | `Settings` (pydantic-settings, env-var backed) |
| [`vlm_scene_description.logger`](../vlm_scene_description/logger.py) | Loguru setup; `LogFormat` enum; `setup_logging()` |


## Logging

All services use [loguru](https://github.com/Delgan/loguru). `setup_logging(fmt, service)` in [`vlm_scene_description.logger`](../vlm_scene_description/logger.py) removes loguru's default handler and installs the configured one.

| Format | Output | Use case |
|---|---|---|
| `colored` (default) | Human-readable with ANSI colours | Local development |
| `json` | One JSON object per line | Production / log aggregators |

Set the format via `VLM_SCENE_DESCRIPTION_LOG_FORMAT=colored|json` or in `.env`.

`setup_logging()` is called once per process entry-point (API lifespan). All other modules just `from loguru import logger`.

## Storage

[`vlm_scene_description.db.base.Repository`](../vlm_scene_description/db/base.py) is an abstract base class with two implementations:

| Implementation | Used in |
|---|---|
| `MemoryRepository` | Tests and local dev (`VLM_SCENE_DESCRIPTION_DB_BACKEND=memory`) |
| `SQLiteRepository` | Production (`VLM_SCENE_DESCRIPTION_DB_BACKEND=sqlite`, path from `VLM_SCENE_DESCRIPTION_DB_PATH`) |

`db/factory.py` selects the implementation from `Settings.db_backend` at startup.

ORM tables are defined in [`vlm_scene_description.db.orm`](../vlm_scene_description/db/orm.py) as subclasses of `Base`. Schema changes are managed with Alembic ([`migrations/`](../migrations/)); the migration URL is derived from `Settings.database_url`, and migrations ship inside the API image so they can run as a Kubernetes init container or job.
