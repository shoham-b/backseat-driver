# Backseat Driver

[![Python Version](https://img.shields.io/badge/python-3.12-blue?logo=python&logoColor=white)](pyproject.toml)
[![Tests Status](https://github.com/shoham-b/backseat-driver/actions/workflows/ci.yml/badge.svg)](https://github.com/shoham-b/backseat-driver/actions/workflows/ci.yml?query=branch%3Amain)
[![Docker Build](https://github.com/shoham-b/backseat-driver/actions/workflows/docker.yml/badge.svg)](https://github.com/shoham-b/backseat-driver/actions/workflows/docker.yml?query=branch%3Amain)
[![CodeQL](https://github.com/shoham-b/backseat-driver/actions/workflows/codeql.yml/badge.svg)](https://github.com/shoham-b/backseat-driver/actions/workflows/codeql.yml?query=branch%3Amain)
[![codecov](https://codecov.io/gh/shoham-b/backseat-driver/graph/badge.svg)](https://codecov.io/gh/shoham-b/backseat-driver)
[![CodSpeed](https://img.shields.io/endpoint?url=https://codspeed.io/badge.json)](https://app.codspeed.io/shoham-b/backseat-driver?utm_source=badge)
[![Docs](https://img.shields.io/badge/docs-github--pages-blue)](https://shoham-b.github.io/backseat-driver/)
[![Generated from python-project-template](https://img.shields.io/badge/generated%20from-python--project--template-8A2BE2)](https://github.com/shoham-b/python-project-template)

**Describe images in natural language with a vision-language model (VLM), and compare models side by side.**

Backseat Driver reads a set of images, asks a VLM to describe each one, and writes the descriptions
out. The model and runtime are swappable behind one interface (a local HuggingFace model, a local
[Ollama](https://ollama.com) server, or the hosted Claude API), and the same code runs as a
one-process script on a laptop or as a queue-backed service on Kubernetes.

The [nuScenes v1.0-mini](https://www.nuscenes.org/nuscenes) driving dataset is the demo input, which is
where the name comes from. It gives the pipeline realistic camera frames and a human-written label to
score against; nothing in the design is specific to it. Built for the "Scene Description via VLM"
take-home assignment (see [home_assignment_vlm.pdf](docs/home_assignment_vlm.pdf)).

## Highlights

- **Pick your model.** `--backend huggingface|ollama|anthropic` and `--model <name>`: terse captions from a
  CPU-only BLIP, or verbose prompt-driven descriptions from `llava` or Claude.
- **Compare models.** Every run writes `output/<backend>__<model>.json`, so results never overwrite each
  other. `just ui` scores them against the nuScenes labels and shows them side by side.
- **One pipeline, three scales.** The same read → process → write code runs in one process, as tasks on a
  thread inside the API, or as separate services over RabbitMQ, S3 and Postgres.
- **Production-shaped.** Ports and adapters, typed, fail-fast, structured logs, a Dockerfile target per
  service, Kubernetes manifests with queue-depth autoscaling, and five layers of tests.

## How it works

```
   read/                     process/                    write/
┌─────────────┐          ┌──────────────┐          ┌──────────────┐
│ SceneLoader │ ───────▶ │  Captioner   │ ───────▶ │  write_json  │
└─────────────┘          └──────────────┘          └──────────────┘
```

1. **Read.** [`NuScenesSceneLoader`](backseat_driver/read/dataset/nuscenes_scene_loader.py) picks one representative
   keyframe per scene and camera (the midpoint of the scene, not the static first frame). The dataset is
   downloaded into `data/sets/nuscenes` on first use.
2. **Process.** A [`Captioner`](backseat_driver/process/captioner.py) pairs a runtime with a model:

   | Backend | Runs | Output style |
   |---|---|---|
   | `huggingface` | a local `image-to-text` pipeline, CPU-only (e.g. `Salesforce/blip-image-captioning-base`) | terse caption |
   | `ollama` | a local Ollama server (e.g. `llava`) | short keyword list in the style of the nuScenes labels |
   | `anthropic` | the hosted Claude API | short keyword list in the style of the nuScenes labels |

3. **Write.** [`write_json`](backseat_driver/write/json_writer.py) writes one object per scene and camera:

   ```json
   {
     "scene_token": "cc8c0bf57f984915a77078b10eb33198",
     "scene_name": "scene-0061",
     "camera_channel": "CAM_FRONT",
     "image_path": "samples/CAM_FRONT/...jpg",
     "reference_description": "Parked truck, construction, intersection, turn left, following a van",
     "description": "a city street with cars and pedestrians",
     "model_name": "Salesforce/blip-image-captioning-base",
     "generated_at": "2026-09-27T12:00:00Z"
   }
   ```

   `image_path` is the image's key below the dataset root. `reference_description` is nuScenes' own label, which `report` and `ui` use to score each model.

The loader and the captioner are abstract ports composed in [`pipeline.py`](backseat_driver/pipeline.py),
which never imports nuscenes-devkit, transformers or torch, so it is unit-tested with fakes. To use a
different dataset, write another [`SceneLoader`](backseat_driver/read/dataset/scene_loader.py); the model side does
not change.

## Quickstart

```bash
# 1. Install dependencies
uv sync --group dev

# 2. Describe the scenes (downloads the dataset and the model on first use)
uv run backseat-driver describe --camera front --model Salesforce/blip-image-captioning-base
# → output/huggingface__Salesforce-blip-image-captioning-base.json

# 3. Compare the models you have run
just ui    # http://localhost:8081
```

No local Python? Run it containerized:

```bash
just docker-run --camera front --model Salesforce/blip-image-captioning-base
```

Setup details, including the HTTP API, are in [docs/getting-started.md](docs/getting-started.md).

## One pipeline, three ways to run it

The three steps never change; each rung adds one thing. [From pipeline to cluster](docs/ladder.md) has
the diagrams and shows where each piece enters the code.

| Rung | Command | What runs | Adds | Needs |
|---|---|---|---|---|
| **1. Pipeline** | `just describe` | read, process and write in one function call | nothing | dataset in `data/` |
| **2. Seam** | `just dev` | the same steps as tasks on a thread inside the API (`POST /jobs`) | an in-process queue and a SQLite job store | dataset in `data/` |
| **3. Machines** | `just up`, `just k8s-apply` | ingest and caption workers as separate services | RabbitMQ, an S3 bucket and Postgres | Docker or a cluster |

`describe --mode distributed` submits the pipeline as a job to a running API and writes the same JSON file
as rung 1. Showing results (`report`, `ui`) is a separate role that only reads what was written. See
[Running it](docs/running.md) for every command side by side.

The API also exposes the captioner directly: `POST /describe` captions one uploaded image, and `POST /jobs`
runs a whole dataset asynchronously.

## Design assumptions

- **Representative frame = the midpoint of the scene's keyframes.** The first frame is often a static
  lead-in. The camera is always an explicit choice: pass `--camera` (repeatable) or `--all-cameras`.
- **A small VLM is fine.** The CPU-only example uses BLIP base (~990MB), per the assignment's "no need for
  large models or GPU inference". There is no default model, so pass `--model` or set the matching
  `BACKSEAT_DRIVER_*_MODEL_NAME`. Any HuggingFace `image-to-text` model works, as do Ollama and Claude models.
- **The dataset is a demo input, not the point.** It is not bundled (its license forbids redistribution), so
  it is downloaded into the gitignored `data/sets/nuscenes` on first use.
- **The batch job is the primary shape.** The assignment describes a pipeline over a set of scenes, so
  `describe` writing one JSON file is the main deliverable; the API is the optional deployment of the same
  pipeline ([why](docs/architecture.md#deployment)).
- **No batching, no GPU.** Scenes are captioned one at a time. Scale comes from more caption workers, not
  from batched inference.

The alternatives considered and why are in [Design decisions](docs/design-decisions.md).

## Documentation

Published at **https://shoham-b.github.io/backseat-driver/**; the source is in [`docs/`](docs).

| Page | What it covers |
|---|---|
| [Getting started](docs/getting-started.md) | Setup, dataset, Docker, the HTTP API, configuration |
| [Running it](docs/running.md) | Every way to run it: CLI, `just`, Docker, Compose, Kubernetes |
| [From pipeline to cluster](docs/ladder.md) | How one pipeline grows into a cluster, with diagrams |
| [Architecture](docs/architecture.md) | Tech stack and object model |
| [Distributed mode](docs/distributed.md) | Services, scaling and delivery guarantees |
| [Deployment](docs/deployment.md) | Images, Compose profiles, Kubernetes manifests, release checklist |
| [Design decisions](docs/design-decisions.md) | The alternatives considered |
| [Development](docs/development.md) | Task list, tests, conventions |
| [CLI](docs/cli.md) and [API](docs/api.md) reference | Commands, and the `backseat_driver.*` modules |

## Testing

Five layers, from fastest to slowest (commands in [docs/development.md](docs/development.md#tests)):

- **Unit** (`tests/unittests/`): no I/O, no model download, no dataset. Heavy dependencies are imported lazily
  inside injected factories, so tests hand in fakes instead of patching anything.
- **Integration** (`tests/integrationtests/`): the FastAPI app in-process, the CLI commands and the
  ingest/caption workers on an in-memory queue and store, plus `schemathesis` fuzzing of the OpenAPI schema.
- **Smoke** (`tests/smoketests/`): black-box HTTP checks against a running API.
- **UI** (`tests/uitests/`): Selenium in headless Chrome against the real comparison UI.
- **System** (`tests/systemtests/`): the full Docker Compose stack.

```bash
just test          # unit + integration, with coverage (the floor is enforced in CI)
just test-ui       # comparison UI, needs Chrome
just test-system   # full system test via Docker Compose
```

## Development

```bash
just describe          # run the pipeline
just ui                # model-comparison UI over ./output (http://localhost:8081)
just dev               # API dev server with hot reload (monolith mode: no broker or database)
just dev-distributed   # same, against RabbitMQ + Postgres in Docker
just fmt               # auto-fix and reformat
just typecheck         # type check
just docs              # build the docs
```

`just --list` shows every recipe. `test-system`, `test-all`, `dev-distributed`, `k8s-up` and `k8s-validate`
are POSIX-only (use WSL or Git Bash on Windows). Codebase conventions are in [AGENTS.md](AGENTS.md).

The project was scaffolded from [python-project-template](https://github.com/shoham-b/python-project-template)
and adapted to this domain; [docs/development.md](docs/development.md) lists what was stripped.

## Deployment

`docker/Dockerfile` has one target per service: `cli` (the pipeline, suited to a scheduled batch job),
`api`, `ingest-worker` and `caption-worker`, built and pushed to `ghcr.io` by
[`.github/workflows/docker.yml`](.github/workflows/docker.yml).

```bash
just docker-run   # the pipeline, containerized
just up           # API + RabbitMQ + Postgres + queue workers
just k8s-apply    # the same stack on Kubernetes (deploy/k8s)

# Model-comparison UI over ./output (http://localhost:8081)
just compose --profile ui up ui --build
```

Kubernetes manifests live in [`deploy/k8s`](deploy/k8s), with optional queue-depth autoscaling via KEDA. See
[docs/deployment.md](docs/deployment.md).

## Configuration

All settings are environment variables (or `.env`) prefixed `BACKSEAT_DRIVER_`. Start from
[.env.example](.env.example); see [docs/getting-started.md#configuration](docs/getting-started.md#configuration).

## License

See [LICENSE](LICENSE).
