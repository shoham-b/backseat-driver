# Backseat Driver

![Python Version](https://img.shields.io/badge/python-3.12-blue?logo=python&logoColor=white)
![Tests Status](https://github.com/shoham-b/backseat-driver/actions/workflows/ci.yml/badge.svg)
[![Docker Build](https://github.com/shoham-b/backseat-driver/actions/workflows/docker.yml/badge.svg)](https://github.com/shoham-b?tab=packages&repo_name=backseat-driver)
![CodeQL](https://github.com/shoham-b/backseat-driver/actions/workflows/codeql.yml/badge.svg)
[![codecov](https://codecov.io/gh/shoham-b/backseat-driver/graph/badge.svg)](https://codecov.io/gh/shoham-b/backseat-driver)
[![CodSpeed](https://img.shields.io/endpoint?url=https://codspeed.io/badge.json)](https://app.codspeed.io/shoham-b/backseat-driver?utm_source=badge)
[![Docs](https://img.shields.io/badge/docs-github--pages-blue)](https://shoham-b.github.io/backseat-driver/)
[![Generated from python-project-template](https://img.shields.io/badge/generated%20from-python--project--template-8A2BE2)](https://github.com/shoham-b/python-project-template)

A small production-shaped service for running vision-language model (VLM) inference over images and
getting back natural-language descriptions, with the model and runtime (HuggingFace, Ollama, Claude) swappable
behind one interface. The [nuScenes v1.0-mini](https://www.nuscenes.org/nuscenes) driving dataset is the demo
input: it shows the pipeline describing a set of scenes end to end, but nothing in the design is specific to it.
Built for the "Scene Description via VLM" take-home assignment (see [home_assignment_vlm.pdf](docs/home_assignment_vlm.pdf)).

## What it does

The demo runs on nuScenes; the loader is the only dataset-specific step.

1. **Loads a scene** — [`scenes/nuscenes_scene_loader.py`](backseat_driver/scenes/nuscenes_scene_loader.py) reads the
   dataset via `nuscenes-devkit` and picks one representative keyframe image per scene and camera (at the
   midpoint of the scene rather than the first frame). The dataset is downloaded into `data/sets/nuscenes` on first use.
2. **Runs a VLM** — a [`Captioner`](backseat_driver/captioning/captioner.py) pairs a runtime with a model:
   a local HuggingFace `image-to-text` model (e.g. `Salesforce/blip-image-captioning-base`, CPU-only, terse captions),
   a local [Ollama](https://ollama.com) server (e.g. `llava`), or the hosted Claude API, the last two for verbose,
   prompt-driven descriptions. Pick one with `--backend` and `--model`.
3. **Outputs the results** — [`scenes/writer.py`](backseat_driver/scenes/writer.py) writes one JSON object
   per scene and camera to `output/<backend>__<model>.json` (e.g. `output/huggingface__Salesforce-blip-image-captioning-base.json`):

   ```json
   [
     {
       "scene_token": "cc8c0bf57f984915a77078b10eb33198",
       "scene_name": "scene-0061",
       "camera_channel": "CAM_FRONT",
       "image_path": "data/sets/nuscenes/samples/CAM_FRONT/...jpg",
       "reference_description": "Parked truck, construction, intersection, turn left, following a van",
       "description": "a city street with cars and pedestrians",
       "model_name": "Salesforce/blip-image-captioning-base",
       "generated_at": "2026-09-27T12:00:00Z"
     }
   ]
   ```

   `reference_description` is nuScenes' own human-written scene label. `backseat-driver report` and `ui` use it to score
   and compare the output files of different models side by side.

Swapping the dataset means writing another [`SceneLoader`](backseat_driver/scenes/scene_loader.py); the VLM side
([`Captioner`](backseat_driver/captioning/captioner.py)) doesn't change. Both are abstract ports composed in
[`scenes/pipeline.py`](backseat_driver/scenes/pipeline.py), so the orchestration logic never imports
nuscenes-devkit, transformers, or torch directly and is fully unit-testable with fakes.

The same captioning is also available as a service: `POST /describe` captions one uploaded image, and `POST /jobs`
runs a whole dataset asynchronously (see [Microservices, or one monolith](#microservices-or-one-monolith)).

## Assumptions

Stated explicitly, per the assignment's request:

- **Representative frame = midpoint of the scene's keyframes.** The first frame is often a static lead-in; the
  midpoint is more likely to show the scene in motion. The camera and the selection policy are the only
  "scene → single image" choice this pipeline makes: pass `--camera` (repeatable) or `--all-cameras`, there is no default.
- **"Small/basic VLM is fine"** is taken literally for the CPU-only example: `Salesforce/blip-image-captioning-base`
  (~990MB) rather than a larger multimodal LLM. There is no default model, so pass `--model` or set the matching
  `BACKSEAT_DRIVER_*_MODEL_NAME`. Any HuggingFace `image-to-text` model works, as do Ollama and Claude models for richer output.
- **The dataset is a demo input, not the point.** The goal is VLM inference; nuScenes just gives it realistic
  images to run on. It is not bundled (its license doesn't permit redistribution), so the loader downloads
  v1.0-mini into `data/sets/nuscenes` (gitignored) on first use and re-downloads when the archive changes.
- **Batch job is the primary shape.** The assignment describes a pipeline over a *set* of scenes, so the CLI
  (`backseat-driver run`) producing one JSON file is the main deliverable. The HTTP API is the optional deployment
  of the same pipeline, answering "how would you deploy this" — see [docs/architecture.md#deployment](docs/architecture.md#deployment).
- **No GPU, no batching.** Scenes are captioned one at a time, and the HuggingFace example runs on CPU, matching "no need for
  large models or GPU inference." For v1.0-mini's 10 scenes this is seconds-to-low-minutes after the model
  is cached. Scale comes from the distributed workers (more caption workers), not from batched inference, which
  `ScenePipeline` doesn't do.

## Quickstart

```bash
# 1. Install deps
uv sync --group dev

# 2. Run the pipeline (downloads the nuScenes v1.0-mini dataset and the model on first use)
uv run backseat-driver run --camera front --model Salesforce/blip-image-captioning-base
# → output/huggingface__Salesforce-blip-image-captioning-base.json

# 3. Compare the models you have run
uv run backseat-driver ui    # http://localhost:8081
```

Or fully containerized, no local Python required:

```bash
just docker-run --camera front --model Salesforce/blip-image-captioning-base
```

Full setup instructions (including the HTTP API) are in
**[docs/getting-started.md](docs/getting-started.md)**. Full documentation is published at
**https://shoham-b.github.io/backseat-driver/**.

## Microservices, or one monolith

Backseat Driver is a **monorepo of microservices**: the API, the ingest and caption workers, the report UI and the batch CLI live in one Python package and are built into one image per service. The same code can also be **debugged as a monolith**: one process runs the API and both workers together, with an in-process queue and a SQLite (or in-memory) job store. Debugging as a monolith drops RabbitMQ, S3 and Postgres, so `just dev` needs nothing but the API. See [Distributed mode](docs/distributed.md) for the microservices and [Running it](docs/running.md) for how to start either.

## How this was tested

Five layers, matching the "structure it as if this was a production project" ask — see
[docs/development.md](docs/development.md#tests) for commands:

- **Unit** (`tests/unittests/`) — no I/O, no model download, no dataset, one unit at a time. `nuscenes-devkit` and
  `transformers` are imported lazily inside injected factories, so tests hand in fakes instead of patching anything.
- **Integration** (`tests/integrationtests/`) — the FastAPI app in-process via `httpx.ASGITransport`, the CLI commands, and
  the ingest/caption workers wired to in-memory queue and store, with fake captioners so no weights are downloaded.
  Includes `schemathesis`-driven fuzzing of the OpenAPI schema.
- **Smoke** (`tests/smoketests/`) — black-box HTTP checks against a running API.
- **UI** (`tests/uitests/`) — Selenium in headless Chrome against the real model-comparison `ui` server.
- **System** (`tests/systemtests/`) — full Docker Compose stack.

```bash
just test          # unit + integration, with coverage (coverage floor enforced in CI)
just test-ui       # model-comparison UI, needs Chrome
just test-system   # full system test via Docker Compose
```

## Deployment

See **[docs/architecture.md#deployment](docs/architecture.md#deployment)** for the full discussion. Short
version: `docker/Dockerfile` has one target per service: `cli` (the pipeline, meant to run as a scheduled batch
job / CronJob), `api`, `ingest-worker` and `caption-worker`. They are built and pushed to `ghcr.io` in
[`.github/workflows/docker.yml`](.github/workflows/docker.yml). `just up` runs the stack in Docker Compose, and
Kubernetes manifests live in [`deploy/k8s`](deploy/k8s) (`kubectl apply -k deploy/k8s`, with optional queue-depth
autoscaling via KEDA); see **[docs/deployment.md](docs/deployment.md)**.

## Development

```bash
just run          # run the pipeline
just ui           # model-comparison UI over ./output (http://localhost:8081)
just dev          # API dev server with hot reload (monolith mode: no broker/database needed)
just dev-distributed  # same, against RabbitMQ + Postgres in Docker
just test         # unit + integration tests
just fmt          # auto-fix and reformat
just typecheck    # type check
just docs         # build docs
```

A few recipes are POSIX-only and absent on Windows: `test-system`, `test-all`, `dev-distributed`, `k8s-up` and
`k8s-validate` (use WSL or Git Bash for those).

See [docs/development.md](docs/development.md) for the full task list and [AGENTS.md](AGENTS.md) for
codebase conventions.

The project was scaffolded from [python-project-template](https://github.com/shoham-b/python-project-template)
(`models/` → capability packages (`captioning/`, `scenes/`, `jobs/`) → `cli/`+`api/`, containerized, CI, typed, tested at four levels)
and then adapted to this domain; [docs/development.md](docs/development.md) lists what was stripped from the generic scaffold.

## Docker

```bash
just docker-run   # the pipeline (primary deliverable)
just up           # API + RabbitMQ + Postgres + queue workers
just k8s-apply    # the same stack on Kubernetes (deploy/k8s)

# Model-comparison UI over ./output (http://localhost:8081)
just compose --profile ui up ui --build
```

See [docs/running.md](docs/running.md) for how these, `just dev` and the CLI fit together.

## Configuration

All settings are read from environment variables (or `.env`), prefixed `BACKSEAT_DRIVER_`. See
[.env.example](.env.example) and [docs/getting-started.md#configuration](docs/getting-started.md#configuration).

## License

See [LICENSE](LICENSE).
