# Architecture

## Tech stack

| Concern | Tech | Why |
|---|---|---|
| Language & packaging | Python 3.12, [uv](https://docs.astral.sh/uv/) | `uv`'s dependency-groups (`core`/`vlm`/`nuscenes`/`cli`/`api`/`dev`/`docs`) let the CLI and API images install only what they each need |
| Task runner | [Justfile](../Justfile) | `just run`, `just dev`, `just test`, `just lint`, `just docs`, ... — one discoverable entry point per workflow |
| CLI | [Typer](https://typer.tiangolo.com/) | The primary entry point (`vlm-scene-description run`) |
| HTTP API | [FastAPI](https://fastapi.tiangolo.com/) + [Granian](https://github.com/emmett-framework/granian) | Optional on-demand deployment shape; Granian as the production ASGI server |
| Domain models & config | [Pydantic](https://docs.pydantic.dev/) / [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) | `SceneKeyframe`/`SceneDescription` schemas; env-var-backed `Settings` |
| Logging | [Loguru](https://github.com/Delgan/loguru) | Structured logs, colored locally / JSON in production |
| VLM backend | [transformers](https://huggingface.co/docs/transformers) `image-to-text` pipeline, BLIP (`Salesforce/blip-image-captioning-base`), CPU-only [torch](https://pytorch.org/), [Pillow](https://python-pillow.org/) | Small captioning model, no GPU required — pinned `transformers<5` since the plain captioning pipeline was folded into a chat-style task in v5 |
| Dataset access | [nuscenes-devkit](https://github.com/nutonomy/nuscenes-devkit) | Reads the nuScenes v1.0-mini dataset |
| Testing | pytest, pytest-asyncio, pytest-cov/coverage, httpx (`ASGITransport`), [hypothesis](https://hypothesis.readthedocs.io/) (property-based), [schemathesis](https://schemathesis.readthedocs.io/) (OpenAPI fuzzing) | Four layers: unit / integration / smoke / system (see `AGENTS.md`) |
| Lint / types | [ruff](https://docs.astral.sh/ruff/), [ty](https://github.com/astral-sh/ty) | `just lint` / `just typecheck` |
| Docs | [MkDocs](https://www.mkdocs.org/) + Material + mkdocstrings | This site, published via GitHub Pages (`.github/workflows/pages.yml`) |
| Containers | Docker (multi-stage `docker/Dockerfile`, `cli` + `api` targets), Docker Compose | See "Deployment" below |
| CI/CD | GitHub Actions — `ci.yml` (lint/typecheck/test), `docker.yml` (build+push images), `codeql.yml`, `release-please.yml`/`release.yml`, `semantic-pr.yml`, `dependabot-auto-merge.yml` | |

## Components

### Entry points

The pipeline logic in `bl/` is shared by two independent entry points:

| Component | Entry point | Description |
|---|---|---|
| **CLI** (primary) | `uv run vlm-scene-description run` | Batch job: reads a whole nuScenes dataset, describes every scene, writes one JSON file. This is what the assignment asks for. |
| **API** (optional) | `just dev` (dev) / `just serve` (production), `:8080` | FastAPI service exposing `/describe` — captions a single uploaded image on demand. Included to demonstrate a second deployment shape for the same captioning logic (see "Deployment" below). |

### Object model

Three roles, deliberately not four — `SceneLoader` and `Captioner` are `Protocol`s because they each have a real reason to vary (dataset backend; VLM backend) and a real reason to be faked in tests (filesystem/dataset I/O; slow model inference). `write_json` stays a plain function — the thing worth typing on the output side is the `SceneDescription` schema itself, not the act of writing it.

```
                              ┌───────────────┐
                              │   Settings     │  config.py — env-var-backed
                              └───────┬───────┘
                                      │ configures
              ┌───────────────────────┼───────────────────────┐
              ▼                       ▼                       ▼
    ┌───────────────────┐   ┌───────────────────┐   ┌──────────────────────┐
    │   SceneLoader      │   │    Captioner       │   │     write_json        │
    │   (Protocol)        │   │    (Protocol)       │   │   (plain function)    │
    │                     │   │                     │   │                       │
    │ NuScenesSceneLoader │   │   BlipCaptioner     │   │ list[SceneDescription]│
    │ — Adapter over       │   │  — Strategy: the     │   │   → JSON file          │
    │ nuscenes-devkit,     │   │  swappable VLM       │   │                       │
    │ returns SceneKeyframe│   │  backend             │   │                       │
    └──────────┬──────────┘   └──────────┬──────────┘   └───────────▲───────────┘
               │ list[SceneKeyframe]      │ str                      │
               └─────────────┬────────────┘                          │
                             ▼                                       │
                    ┌────────────────────┐                           │
                    │    ScenePipeline    │  bl/pipeline.py           │
                    │  Facade/orchestrator│  — constructor-injected   │
                    │  loader → captioner │     with both Protocols,  │
                    │  per scene           │     never imports         │
                    └──────────┬──────────┘     nuscenes/transformers │
                               │ list[SceneDescription]                │
                               └───────────────────────────────────────┘
```

| Object | Kind | Pattern role |
|---|---|---|
| `SceneKeyframe`, `SceneDescription` | Pydantic model | Value object — pure data, no behavior |
| `SceneLoader` / `NuScenesSceneLoader` | Protocol / implementation | Adapter — isolates the rest of the app from `nuscenes-devkit`'s dict-shaped API |
| `Captioner` / `BlipCaptioner` | Protocol / implementation | Strategy — swappable VLM backend (unit tests inject a fake) |
| `ScenePipeline` | Class | Facade — one `run()` entry point over loader→captioner, no I/O or model logic of its own |
| `write_json` | Function | — deliberately *not* promoted to a class; nothing varies here yet |
| `Settings` | pydantic-settings class | Single typed source of config, read once per process |

## Data flow

```
CLI path (batch):

┌──────────────────────┐   ┌──────────────────────┐   ┌──────────────────────┐
│  NuScenesSceneLoader  │──▶│     ScenePipeline     │──▶│      write_json      │
│  reads dataset JSON,  │   │  loader → captioner   │   │  list[SceneDescription]│
│  picks one keyframe   │   │  per scene            │   │  → output/*.json      │
│  image per scene      │   │                        │   │                      │
└──────────────────────┘   └───────────┬────────────┘   └──────────────────────┘
                                        │
                                        ▼
                              ┌──────────────────┐
                              │   BlipCaptioner   │
                              │  HF image-to-text │
                              │  pipeline (lazy)   │
                              └──────────────────┘

API path (on-demand, optional):

┌────────────┐   HTTP POST    ┌───────────────────────┐   Python call   ┌──────────────────┐
│   Client    │───/describe──▶│  api/routers/describe  │────────────────▶│   BlipCaptioner   │
└────────────┘   (image)      └───────────────────────┘                 └──────────────────┘
```

## Layer design

```
models/            bl/                        cli/ | api/
──────────         ───────────                ─────────────
Domain models  →   Business logic         →    Entry points
Pure Pydantic      No HTTP, no nuscenes/        cli/run.py drives the batch
No dependencies    transformers imports at      pipeline; api/routers/describe.py
                   module scope — only          drives the on-demand endpoint.
                   inside methods (lazy)
```

Each layer only imports from layers to its left:

- **`models/`** — pure Pydantic models (`SceneKeyframe`, `SceneDescription`). No imports from `api/`, `bl/`, or `cli/`.
- **`bl/`** — business logic. `nuscenes_loader.SceneLoader` and `captioner.Captioner` are Protocols; `pipeline.ScenePipeline` is built from them via constructor injection, so it never imports nuscenes-devkit, transformers, or torch — those stay behind lazy imports inside the concrete implementations, which keeps `ScenePipeline` fast and trivially testable with fakes.
- **`api/`** — HTTP layer. Imports `bl` and `models`. Owns request validation, response serialization, and error mapping.
- **`cli/`** — Typer commands. Wires concrete `bl/` implementations together and drives the pipeline or a test suite.

## API contracts

### HTTP API (`vlmscene.api`)

Successes return the documented model directly. Errors use `{"error": {"code": <int>, "status": "<phrase>", "message": "<detail>"}}`.

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Liveness probe — returns 200 if the process is running, no dependency checks |
| `GET` | `/ready` | Readiness probe — returns 200 only when the captioner is available; 503 otherwise |
| `POST` | `/describe` | Multipart image upload → `{"description": str, "model_name": str}` |

## Module responsibilities

| Package | Responsibility |
|---|---|
| [`vlmscene.models`](../vlmscene/models/__init__.py) | `SceneKeyframe`, `SceneDescription` — shared domain models (Pydantic) |
| [`vlmscene.bl`](../vlmscene/bl/) | `SceneLoader`/`NuScenesSceneLoader`, `Captioner`/`BlipCaptioner`, `ScenePipeline`, `write_json` |
| [`vlmscene.cli`](../vlmscene/cli/) | Typer CLI: `run` (the pipeline) and `test smoke` |
| [`vlmscene.api`](../vlmscene/api/) | FastAPI app, routes, lifespan, exception handlers |
| [`vlmscene.config`](../vlmscene/config.py) | `Settings` (pydantic-settings, env-var backed) |
| [`vlmscene.logger`](../vlmscene/logger.py) | Loguru setup; `LogFormat` enum; `setup_logging()` |

## Logging

All entry points use [loguru](https://github.com/Delgan/loguru). `setup_logging(fmt, service)` in [`vlmscene.logger`](../vlmscene/logger.py) removes loguru's default handler and installs the configured one.

| Format | Output | Use case |
|---|---|---|
| `colored` (default) | Human-readable with ANSI colours | Local development |
| `json` | One JSON object per line | Production / log aggregators |

Set the format via `VLM_SCENE_DESCRIPTION_LOG_FORMAT=colored|json` or in `.env`.

`setup_logging()` is called once per process entry-point (API lifespan, CLI `run` command). All other modules just `from loguru import logger`.

## Deployment

The assignment's "how would you deploy this" question has two honest answers depending on how the result is consumed:

1. **Scheduled batch job (the primary use case here).** The `cli` Docker image (`docker/Dockerfile`, target `cli`) runs `vlm-scene-description run` as its entrypoint. In production this is a cron job / scheduled Kubernetes `CronJob` / Airflow task that mounts the dataset (or pulls it from object storage first), runs the pipeline, and writes the resulting JSON to a bucket or a database table. There's no need for a long-running process — this is exactly a "run to completion" container.
2. **On-demand inference service.** If descriptions need to be generated synchronously (e.g. as new images arrive from a real pipeline), the same `BlipCaptioner` is exposed over HTTP via the `api` image and target — a standard horizontally-scaled stateless service behind a load balancer, with `/health`/`/ready` wired to k8s liveness/readiness probes.

Both images share `bl/`, so there is one place that owns "how we caption an image," and two thin, independently deployable wrappers around it.
