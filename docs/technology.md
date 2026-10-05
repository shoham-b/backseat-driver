# Technology

What the project is built with and how it is run. For how the pieces fit together, see [From pipeline to cluster](ladder.md); for the HTTP interface, see [APIs](apis.md).

## Tech stack

| Concern | Tech | Why |
|---|---|---|
| Language & packaging | Python 3.14, [uv](https://docs.astral.sh/uv/) | `uv` dependency groups (`core`, `vlm`, `nuscenes`, `jobs`, `object-storage`, `report`, one per service image, plus `dev`, `docs` and `systemtest`) let each image install only what it needs |
| Task runner | [Justfile](https://github.com/shoham-b/backseat-driver/blob/main/Justfile) | `just describe`, `just dev`, `just test`, `just lint`, `just docs`, ... — one discoverable entry point per workflow |
| CLI | [Typer](https://typer.tiangolo.com/) | The primary entry point (`backseat-driver describe`) |
| HTTP API | [FastAPI](https://fastapi.tiangolo.com/) (`fastapi dev` / `fastapi run`) | Optional on-demand deployment shape; served by the FastAPI CLI (uvicorn) |
| Domain models & config | [Pydantic](https://docs.pydantic.dev/) / [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) | `SceneKeyframe`/`SceneDescription` schemas; env-var-backed `Settings` |
| Logging | [Loguru](https://github.com/Delgan/loguru) | Structured logs, colored locally / JSON in production |
| VLM backends | HuggingFace [transformers](https://huggingface.co/docs/transformers) `image-to-text` pipeline (e.g. BLIP, CPU-only [torch](https://pytorch.org/), [Pillow](https://python-pillow.org/)); a local [Ollama](https://ollama.com) server; the hosted Claude API (the last two over one shared async [httpx](https://www.python-httpx.org/) client) | One backend per runtime, chosen by `BACKSEAT_DRIVER_VLM_BACKEND`. The HuggingFace path needs no GPU. It relies on the plain `image-to-text` pipeline task, so `transformers` is version-pinned in `pyproject.toml`|
| Demo dataset | [nuScenes](https://www.nuscenes.org/) v1.0-mini, read as plain JSON tables (`NuScenesTables`) | The dataset the pipeline is demonstrated on; swappable behind `SceneLoader`. The devkit is not used: it is slow to import and ingest pays that on every message |
| Testing | pytest, pytest-asyncio, pytest-cov/coverage, httpx (`ASGITransport`), [hypothesis](https://hypothesis.readthedocs.io/) (property-based), [schemathesis](https://schemathesis.readthedocs.io/) (OpenAPI fuzzing) | Five layers: unit / integration / smoke / UI / system (see `AGENTS.md`) |
| Lint / types | [ruff](https://docs.astral.sh/ruff/), [ty](https://github.com/astral-sh/ty) | `just lint` / `just typecheck` |
| Docs | [MkDocs](https://www.mkdocs.org/) + Material + mkdocstrings | This site, published via GitHub Pages (`.github/workflows/pages.yml`) |
| Containers | Docker (multi-stage `docker/Dockerfile`, one target per service: `cli`, `api`, `ingest-worker`, `caption-worker`), Docker Compose | See "Deployment shapes" below |
| CI/CD | GitHub Actions — `ci.yml` (lint/typecheck/test), `docker.yml` (build+push images), `codeql.yml`, `release-please.yml` (release, wheel/sdist, version-tagged images), `semantic-pr.yml`, `dependabot-auto-merge.yml` | |

## Logging

All entry points use [loguru](https://github.com/Delgan/loguru). `setup_logging(fmt, service)` in [`backseat_driver.logger`](https://github.com/shoham-b/backseat-driver/blob/main/backseat_driver/logger.py) removes loguru's default handler and installs the configured one.

| Format | Output | Use case |
|---|---|---|
| `colored` (default) | Human-readable with ANSI colours | Local development |
| `json` | One JSON object per line | Production / log aggregators |

Set the format via `BACKSEAT_DRIVER_LOG_FORMAT=colored|json` or in `.env`.

`setup_logging()` is called once per process entry-point (API lifespan, CLI `describe` command). All other modules just `from loguru import logger`.

## Deployment shapes

The assignment's "how would you deploy this" question has two honest answers depending on how the result is consumed:

1. **Scheduled batch job (the primary use case here).** The `cli` Docker image (`docker/Dockerfile`, target `cli`) runs `backseat-driver describe` as its entrypoint. In production this is a cron job / scheduled Kubernetes `CronJob` / Airflow task that mounts the dataset (or pulls it from object storage first), runs the pipeline, and writes the resulting JSON to a bucket or a database table. (The example `Job`, `deploy/k8s/examples/run-job.yaml`, is the distributed variant: it runs `describe --mode distributed`, mounts nothing and leaves the reading to the workers.) There's no need for a long-running process — this is exactly a "run to completion" container.
2. **On-demand inference service.** If descriptions need to be generated synchronously (e.g. as new images arrive from a real pipeline), the same `Captioner` is exposed over HTTP via the `api` image and target — a standard horizontally-scaled stateless service behind a load balancer, with `/health`/`/ready` wired to k8s liveness/readiness probes.

Both images share `process/`, so there is one place that owns "how we caption an image," and two thin, independently deployable wrappers around it.
