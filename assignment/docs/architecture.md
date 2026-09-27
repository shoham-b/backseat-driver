# Architecture

## Components

The pipeline logic in `bl/` is shared by two independent entry points:

| Component | Entry point | Description |
|---|---|---|
| **CLI** (primary) | `uv run vlm_scene_description run` | Batch job: reads a whole nuScenes dataset, describes every scene, writes one JSON file. This is what the assignment asks for. |
| **API** (optional) | `just dev` (dev) / `just serve` (production), `:8080` | FastAPI service exposing `/describe` — captions a single uploaded image on demand. Included to demonstrate a second deployment shape for the same captioning logic (see "Deployment" below). |

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

### HTTP API (`vlm_scene_description.api`)

Successes return the documented model directly. Errors use `{"error": {"code": <int>, "status": "<phrase>", "message": "<detail>"}}`.

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Liveness probe — returns 200 if the process is running, no dependency checks |
| `GET` | `/ready` | Readiness probe — returns 200 only when the captioner is available; 503 otherwise |
| `POST` | `/describe` | Multipart image upload → `{"description": str, "model_name": str}` |

## Module responsibilities

| Package | Responsibility |
|---|---|
| [`vlm_scene_description.models`](../vlm_scene_description/models/__init__.py) | `SceneKeyframe`, `SceneDescription` — shared domain models (Pydantic) |
| [`vlm_scene_description.bl`](../vlm_scene_description/bl/) | `SceneLoader`/`NuScenesSceneLoader`, `Captioner`/`BlipCaptioner`, `ScenePipeline`, `write_json` |
| [`vlm_scene_description.cli`](../vlm_scene_description/cli/) | Typer CLI: `run` (the pipeline) and `test smoke` |
| [`vlm_scene_description.api`](../vlm_scene_description/api/) | FastAPI app, routes, lifespan, exception handlers |
| [`vlm_scene_description.config`](../vlm_scene_description/config.py) | `Settings` (pydantic-settings, env-var backed) |
| [`vlm_scene_description.logger`](../vlm_scene_description/logger.py) | Loguru setup; `LogFormat` enum; `setup_logging()` |

## Logging

All entry points use [loguru](https://github.com/Delgan/loguru). `setup_logging(fmt, service)` in [`vlm_scene_description.logger`](../vlm_scene_description/logger.py) removes loguru's default handler and installs the configured one.

| Format | Output | Use case |
|---|---|---|
| `colored` (default) | Human-readable with ANSI colours | Local development |
| `json` | One JSON object per line | Production / log aggregators |

Set the format via `VLM_SCENE_DESCRIPTION_LOG_FORMAT=colored|json` or in `.env`.

`setup_logging()` is called once per process entry-point (API lifespan, CLI `run` command). All other modules just `from loguru import logger`.

## Deployment

The assignment's "how would you deploy this" question has two honest answers depending on how the result is consumed:

1. **Scheduled batch job (the primary use case here).** The `cli` Docker image (`docker/Dockerfile`, target `cli`) runs `vlm_scene_description run` as its entrypoint. In production this is a cron job / scheduled Kubernetes `CronJob` / Airflow task that mounts the dataset (or pulls it from object storage first), runs the pipeline, and writes the resulting JSON to a bucket or a database table. There's no need for a long-running process — this is exactly a "run to completion" container.
2. **On-demand inference service.** If descriptions need to be generated synchronously (e.g. as new images arrive from a real pipeline), the same `BlipCaptioner` is exposed over HTTP via the `api` image and target — a standard horizontally-scaled stateless service behind a load balancer, with `/health`/`/ready` wired to k8s liveness/readiness probes.

Both images share `bl/`, so there is one place that owns "how we caption an image," and two thin, independently deployable wrappers around it.
