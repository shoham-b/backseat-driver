# Architecture

## Tech stack

| Concern | Tech | Why |
|---|---|---|
| Language & packaging | Python 3.12, [uv](https://docs.astral.sh/uv/) | `uv`'s dependency-groups (`core`/`vlm`/`nuscenes`/`cli`/`api`/`dev`/`docs`) let the CLI and API images install only what they each need |
| Task runner | [Justfile](../Justfile) | `just describe`, `just dev`, `just test`, `just lint`, `just docs`, ... — one discoverable entry point per workflow |
| CLI | [Typer](https://typer.tiangolo.com/) | The primary entry point (`backseat-driver describe`) |
| HTTP API | [FastAPI](https://fastapi.tiangolo.com/) (`fastapi dev` / `fastapi run`) | Optional on-demand deployment shape; served by the FastAPI CLI (uvicorn) |
| Domain models & config | [Pydantic](https://docs.pydantic.dev/) / [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) | `SceneKeyframe`/`SceneDescription` schemas; env-var-backed `Settings` |
| Logging | [Loguru](https://github.com/Delgan/loguru) | Structured logs, colored locally / JSON in production |
| VLM backends | HuggingFace [transformers](https://huggingface.co/docs/transformers) `image-to-text` pipeline (e.g. BLIP, CPU-only [torch](https://pytorch.org/), [Pillow](https://python-pillow.org/)); a local [Ollama](https://ollama.com) server; the hosted Claude API (the last two over a stdlib `urllib` HTTP client) | One backend per runtime, chosen by `BACKSEAT_DRIVER_VLM_BACKEND`. The HuggingFace path needs no GPU — pinned `transformers<5` since the plain captioning pipeline was folded into a chat-style task in v5 |
| Demo dataset | [nuscenes-devkit](https://github.com/nutonomy/nuscenes-devkit) | Reads the nuScenes v1.0-mini dataset the pipeline is demonstrated on; swappable behind `SceneLoader` |
| Testing | pytest, pytest-asyncio, pytest-cov/coverage, httpx (`ASGITransport`), [hypothesis](https://hypothesis.readthedocs.io/) (property-based), [schemathesis](https://schemathesis.readthedocs.io/) (OpenAPI fuzzing) | Five layers: unit / integration / smoke / UI / system (see `AGENTS.md`) |
| Lint / types | [ruff](https://docs.astral.sh/ruff/), [ty](https://github.com/astral-sh/ty) | `just lint` / `just typecheck` |
| Docs | [MkDocs](https://www.mkdocs.org/) + Material + mkdocstrings | This site, published via GitHub Pages (`.github/workflows/pages.yml`) |
| Containers | Docker (multi-stage `docker/Dockerfile`, one target per service: `cli`, `api`, `ingest-worker`, `caption-worker`), Docker Compose | See "Deployment" below |
| CI/CD | GitHub Actions — `ci.yml` (lint/typecheck/test), `docker.yml` (build+push images), `codeql.yml`, `release-please.yml` (release, wheel/sdist, version-tagged images), `semantic-pr.yml`, `dependabot-auto-merge.yml` | |

## The shape

The program is three stages, one package each. `pipeline.py` runs them in a row and `backseat-driver describe` is that, in one process:

```
   read/                       process/                     write/
┌──────────────┐          ┌────────────────┐          ┌────────────────┐
│ SceneLoader  │ ───────▶ │   Captioner    │ ───────▶ │  write_json    │
│ ImageStore   │ keyframes│ BackendCaptioner│ descriptions│ output/*.json │
└──────────────┘          └────────────────┘          └────────────────┘
```

Scaling it out adds one thing, a queue between read and process, and what the queue forces once it crosses machines. [From pipeline to cluster](ladder.md) walks through the three rungs with diagrams. In short:

```
read/ ──▶ IngestWorker ═ transport/ queue ═▶ CaptionWorker ──▶ write/
  │                                                │
  └ read/s3/   images in a bucket                  └ write/job_store/   results in a database
```

Showing the results (`show/`) is a separate role that reads what was written.

### Entry points

| Component | Entry point | Description |
|---|---|---|
| **`describe`** (primary) | `uv run backseat-driver describe` | Reads a nuScenes dataset, describes every scene, writes one JSON file. With `--mode distributed` it submits the same job to the API and its workers. |
| **API** | `just dev` (monolith) / `just serve`, `:8080` | `POST /jobs` runs the pipeline as tasks (in-process, or on workers when `BACKSEAT_DRIVER_MODE=distributed`); `/describe` captions one uploaded image; `/images/{key}` serves keyframes. |
| **Workers** | `backseat-driver worker ingest\|caption` | The two ends of the queue, as separate services. |
| **Show** | `backseat-driver report`, `just ui` | The model-comparison page over JSON files or the API's jobs. The UI is a small FastAPI app (`fastapi run`), not a CLI command. |

### Object model

Each stage has one port, because each has a real reason to vary and a real reason to be faked in tests: `SceneLoader` (dataset backend), `Captioner` (VLM backend) and, on the write side, a JSON writer or a `JobStore`. Each added layer is likewise one port with a local and a remote adapter.

| Object | Kind | Role |
|---|---|---|
| [`SceneKeyframe`, `SceneDescription`](../backseat_driver/models/scene.py) | Pydantic model | Value object: what goes in and what comes out, at every rung |
| [`SceneLoader`](../backseat_driver/read/scene_loader.py) / [`NuScenesSceneLoader`](../backseat_driver/read/nuscenes_scene_loader.py) | Port / adapter | Isolates the rest of the app from `nuscenes-devkit`'s dict-shaped API |
| [`ImageStore`](../backseat_driver/read/image_store.py) / [`LocalImageStore`](../backseat_driver/read/local_image_store.py), [`S3DatasetStore`](../backseat_driver/read/s3/s3_dataset_store.py) | Port / adapters | Where an image's bytes come from: the local disk, or a bucket |
| [`Captioner`](../backseat_driver/process/captioner.py) / [`BackendCaptioner`](../backseat_driver/process/backend_captioner.py) (`CaptionBackend` + `CaptionModel`) | Port / composition | Strategy: the runtime (HuggingFace/Ollama/Anthropic) and the model are swapped independently |
| [`ScenePipeline`, `describe_keyframe`](../backseat_driver/pipeline.py) | Class, function | Rung 1: loader to captioner. `describe_keyframe` is the unit the caption worker also calls |
| [`write_json`](../backseat_driver/write/json_writer.py) | Function | The monolith's write: the list, once, at the end |
| [`JobQueue`](../backseat_driver/transport/job_queue.py) / [`InProcessJobQueue`](../backseat_driver/transport/in_process_job_queue.py), [`CeleryJobQueue`](../backseat_driver/transport/celery_job_queue.py) | Port / adapters | The seam between read and process |
| [`JobStore`](../backseat_driver/write/job_store/job_store.py) / [`InMemoryJobStore`](../backseat_driver/write/job_store/in_memory_job_store.py), [`SqlJobStore`](../backseat_driver/write/job_store/sql_job_store.py) | Port / adapters | The distributed write: one row per description |
| [`IngestWorker`](../backseat_driver/transport/ingest_worker.py), [`CaptionWorker`](../backseat_driver/transport/caption_worker.py) | Classes | The read step as a producer, and process + write per task |
| [`Settings`](../backseat_driver/config.py) | pydantic-settings class | Single typed source of config, read once per process |

## Layer design

```
models/   ──▶   read/  process/  write/  pipeline.py   ──▶   transport/ · read/s3/ · write/job_store/   ──▶   cli/ | api/ | show/
pure            the core: complete on its own                  the added layers: only needed when             entry points
Pydantic        (rung 1)                                       the process step runs elsewhere
```

Each layer only imports from layers to its left:

- **`models/`**: pure Pydantic models (`SceneKeyframe`, `SceneDescription`, `Job`, the queue messages). No imports from any other package.
- **`errors.py`**: the `BackseatDriverError` hierarchy, shared by every package and mapped to HTTP codes by `api/`.
- **The core** (`read/`, `process/`, `write/`, `pipeline.py`): each package holds a port and its adapters. `pipeline.py` and the other orchestration code depend only on the ports through constructor injection and never import nuscenes-devkit, transformers, torch, Celery or SQLAlchemy. Those stay inside the adapter modules, behind lazy imports where heavy.
- **The added layers** (`transport/`, `read/s3/`, `write/job_store/`): everything that exists only because the process step can run on another machine. The core never imports them, and `tests/unittests/test_layering.py` enforces it.
- **`api/`**: the HTTP layer. Imports the ports and `models`. Owns request validation, response serialization and error mapping.
- **[`stacks.py`](../backseat_driver/stacks.py)**: the wiring: which adapter each rung plugs into each port, in one file. The CLI, the API and the workers call it instead of choosing adapters themselves.
- **`cli/`**: Typer commands, thin entry points that build the real collaborators (through `stacks.py`) and call the classes above.
- **`show/`**: the report and UI. Reads descriptions, never writes them.

## API contracts

### HTTP API (`backseat_driver.api`)

Successes return the documented model directly. Errors use `{"error": {"code": <int>, "status": "<phrase>", "message": "<detail>"}}`.

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Liveness probe — returns 200 if the process is running, no dependency checks |
| `GET` | `/ready` | Readiness probe — returns 200 only when the captioner is available; 503 otherwise |
| `POST` | `/describe` | Multipart image upload → `{"description": str, "model_name": str}` |

## Module responsibilities

| Package | Responsibility |
|---|---|
| [`backseat_driver.models`](../backseat_driver/models/__init__.py) | Shared domain models (Pydantic), one module per subject: `scene.py` (`SceneKeyframe`, `SceneDescription`), `job.py` (`Job`, `JobState`, `JobReference`), `tasks.py` (`IngestTask`, `CaptionTask`) |
| [`backseat_driver.process`](../backseat_driver/process/) | `Captioner` port plus `CaptionBackend`s: `HuggingFaceBackend` (BLIP, terse), `OllamaBackend` and `AnthropicBackend` (prompt-driven keyword lists), each running a `CaptionModel`, chosen via `build_captioner` |
| [`backseat_driver.read`](../backseat_driver/read/) | `SceneLoader`, `ImageStore`, the nuScenes loader and local store; `read/s3/` is the bucket-backed variant (distributed) |
| [`backseat_driver.write`](../backseat_driver/write/) | `write_json`; `write/job_store/` holds the `JobStore` port and its SQLite/Postgres adapters (distributed) |
| [`backseat_driver.pipeline`](../backseat_driver/pipeline.py) | `ScenePipeline` and `describe_keyframe`: read then process |
| [`backseat_driver.transport`](../backseat_driver/transport/) | `JobQueue` port, in-process and Celery queues, `IngestWorker`/`CaptionWorker`, `ApiJobClient` |
| [`backseat_driver.show`](../backseat_driver/show/) | Model-comparison report and UI over JSON files or the API |
| [`backseat_driver.errors`](../backseat_driver/errors.py) | `BackseatDriverError` hierarchy |
| [`backseat_driver.cli`](../backseat_driver/cli/) | Typer CLI: `describe` (read, process, write), `report`/`ui` (show), `worker`/`db`/`dataset` (scale out) and `test smoke` |
| [`backseat_driver.api`](../backseat_driver/api/) | FastAPI app, routes, lifespan, exception handlers |
| [`backseat_driver.config`](../backseat_driver/config.py) | `Settings` (pydantic-settings, env-var backed) |
| [`backseat_driver.logger`](../backseat_driver/logger.py) | Loguru setup; `LogFormat` enum; `setup_logging()` |

## Logging

All entry points use [loguru](https://github.com/Delgan/loguru). `setup_logging(fmt, service)` in [`backseat_driver.logger`](../backseat_driver/logger.py) removes loguru's default handler and installs the configured one.

| Format | Output | Use case |
|---|---|---|
| `colored` (default) | Human-readable with ANSI colours | Local development |
| `json` | One JSON object per line | Production / log aggregators |

Set the format via `BACKSEAT_DRIVER_LOG_FORMAT=colored|json` or in `.env`.

`setup_logging()` is called once per process entry-point (API lifespan, CLI `describe` command). All other modules just `from loguru import logger`.

## One pipeline, three ways to run it

Backseat Driver is one idea: **read** the scenes, **process** each image with a vision-language model, **write** the descriptions. `describe` runs it in one process, and that is the whole program. The same three steps can also run as tasks over a queue: in one process for local development (`just dev`, no broker, bucket or database), or as separate services where RabbitMQ sits between read and process, the dataset lives in S3 and the results in Postgres. Showing the results (`report`, `ui`) is a separate role that only reads what was written. See [From pipeline to cluster](ladder.md) for the three rungs and where each piece enters the code, and [Running it](running.md) for how to start each.

## Deployment

The assignment's "how would you deploy this" question has two honest answers depending on how the result is consumed:

1. **Scheduled batch job (the primary use case here).** The `cli` Docker image (`docker/Dockerfile`, target `cli`) runs `backseat-driver describe` as its entrypoint. In production this is a cron job / scheduled Kubernetes `CronJob` / Airflow task that mounts the dataset (or pulls it from object storage first), runs the pipeline, and writes the resulting JSON to a bucket or a database table. (The example `Job`, `deploy/k8s/examples/run-job.yaml`, is the distributed variant: it runs `describe --mode distributed`, mounts nothing and leaves the reading to the workers.) There's no need for a long-running process — this is exactly a "run to completion" container.
2. **On-demand inference service.** If descriptions need to be generated synchronously (e.g. as new images arrive from a real pipeline), the same `Captioner` is exposed over HTTP via the `api` image and target — a standard horizontally-scaled stateless service behind a load balancer, with `/health`/`/ready` wired to k8s liveness/readiness probes.

Both images share `process/`, so there is one place that owns "how we caption an image," and two thin, independently deployable wrappers around it.
