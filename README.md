# VLM Scene Description

![Python Version](https://img.shields.io/badge/python-3.12-blue?logo=python&logoColor=white)
![Tests Status](https://github.com/shoham-b/vlm_scene_description/actions/workflows/ci.yml/badge.svg)
![Docker Build](https://github.com/shoham-b/vlm_scene_description/actions/workflows/docker.yml/badge.svg)
![CodeQL](https://github.com/shoham-b/vlm_scene_description/actions/workflows/codeql.yml/badge.svg)
[![codecov](https://codecov.io/gh/shoham-b/vlm_scene_description/graph/badge.svg)](https://codecov.io/gh/shoham-b/vlm_scene_description)
[![Docs](https://img.shields.io/badge/docs-github--pages-blue)](https://shoham-b.github.io/vlm_scene_description/)
[![Generated from python-project-template](https://img.shields.io/badge/generated%20from-python--project--template-8A2BE2)](https://github.com/shoham-b/python-project-template)

A small production-shaped pipeline that reads driving scenes from the [nuScenes v1.0-mini](https://www.nuscenes.org/nuscenes)
dataset, describes each one with a vision-language model, and writes the results out as JSON — built
for the "Scene Description via VLM" take-home assignment (see [home_assignment_vlm.pdf](home_assignment_vlm.pdf)).

Scaffolded from [python-project-template](https://github.com/shoham-b/python-project-template)
(layered `models/` → `bl/` → `cli/`+`api/`, containerized, CI, typed, tested at four levels) and then
adapted to this domain — see [docs/development.md](docs/development.md) for what was stripped from the
generic scaffold.

## What it does

1. **Loads a scene** — [`bl/nuscenes_loader.py`](vlmscene/bl/nuscenes_loader.py) reads the
   dataset via `nuscenes-devkit` and picks one representative keyframe image per scene (the front camera
   by default, at the midpoint of the scene rather than the first frame).
2. **Runs a VLM** — [`bl/captioner.py`](vlmscene/bl/captioner.py) passes that image through
   a small HuggingFace image-captioning model (`Salesforce/blip-image-captioning-base` by default, CPU-only)
   to produce a short natural-language description.
3. **Outputs the results** — [`bl/writer.py`](vlmscene/bl/writer.py) writes one JSON object
   per scene to `output/scene_descriptions.json`:

   ```json
   [
     {
       "scene_token": "cc8c0bf57f984915a77078b10eb33198",
       "scene_name": "scene-0061",
       "camera_channel": "CAM_FRONT",
       "image_path": "data/sets/nuscenes/samples/CAM_FRONT/...jpg",
       "description": "a city street with cars and pedestrians",
       "model_name": "Salesforce/blip-image-captioning-base",
       "generated_at": "2026-09-27T12:00:00Z"
     }
   ]
   ```

All three steps are Protocol-based ([`SceneLoader`](vlmscene/bl/nuscenes_loader.py),
[`Captioner`](vlmscene/bl/captioner.py)) and composed in
[`bl/pipeline.py`](vlmscene/bl/pipeline.py), so the orchestration logic never imports
nuscenes-devkit, transformers, or torch directly and is fully unit-testable with fakes.

## Assumptions

Stated explicitly, per the assignment's request:

- **Representative frame = midpoint of the scene's `CAM_FRONT` keyframes.** The first frame is often a
  static lead-in; the midpoint is more likely to show the scene in motion. Both the camera and the
  selection policy are the only "scene → single image" choice this pipeline makes — swap `--camera` for
  another channel if front-camera isn't representative enough for your use case.
- **"Small/basic VLM is fine"** is taken literally: `Salesforce/blip-image-captioning-base` (~990MB,
  CPU-only) rather than a larger multimodal LLM. It's swappable via `--model` / `VLM_SCENE_DESCRIPTION_VLM_MODEL_NAME`
  to any HuggingFace `image-to-text` pipeline model.
- **The dataset is not bundled.** nuScenes requires free registration and its license doesn't permit
  redistribution, so it's expected to be downloaded separately and mounted/volume-copied into
  `data/sets/nuscenes` (gitignored). See [Quickstart](#quickstart) below.
- **Batch job, not a request/response service, is the primary shape.** The assignment describes a
  pipeline over a *set* of scenes, so the CLI (`vlm-scene-description run`) producing one JSON file is the
  main deliverable. A small optional HTTP API (`/describe`) is included to concretely answer "how would
  you deploy this" for the on-demand case — see [docs/architecture.md#deployment](docs/architecture.md#deployment).
- **No GPU, no batching/parallelism.** Scenes are captioned one at a time on CPU, matching "no need for
  large models or GPU inference." For v1.0-mini's 10 scenes this is seconds-to-low-minutes after the model
  is cached; a larger dataset would want batched inference, which `ScenePipeline` doesn't currently do.

## Quickstart

```bash
# 1. Install deps
uv sync --group dev

# 2. Get the dataset (one-time; see docs/getting-started.md for details)
#    Download v1.0-mini from https://www.nuscenes.org/nuscenes#download and extract to:
#    data/sets/nuscenes/{maps,samples,sweeps,v1.0-mini}

# 3. Run the pipeline
uv run vlm-scene-description run
# → output/scene_descriptions.json
```

Or fully containerized, no local Python required:

```bash
docker compose --profile cli run --rm cli
```

Full setup instructions (including the optional HTTP API) are in
**[docs/getting-started.md](docs/getting-started.md)**. Full documentation is published at
**https://shoham-b.github.io/vlm_scene_description/**.

## How this was tested

Four layers, matching the "structure it as if this was a production project" ask — see
[docs/development.md](docs/development.md#tests) for commands:

- **Unit** (`tests/unittests/`) — no I/O, no model download, no dataset. `bl/nuscenes_loader.py` and
  `bl/captioner.py` import nuscenes-devkit/transformers lazily inside methods specifically so these tests
  can monkeypatch them out (fake `NuScenes` class, fake `transformers.pipeline`) and run in milliseconds.
  Covers the middle-frame selection logic, missing-camera error handling, pipeline orchestration
  (including `--max-scenes` and empty-dataset edge cases), and the JSON writer.
- **Integration** (`tests/integrationtests/`) — FastAPI's optional `/describe`/`/health`/`/ready` in-process
  via `httpx.ASGITransport`, with a `FakeCaptioner` swapped in so no model weights are downloaded during
  tests. Includes `schemathesis`-driven fuzzing of the OpenAPI schema.
- **Smoke** (`tests/smoketests/`) — black-box HTTP checks against a running API.
- **System** (`tests/systemtests/`) — full Docker Compose stack.

```bash
just test          # unit + integration, with coverage (min 80%, enforced in CI)
just test-compose  # full system test via Docker Compose
```

The CLI pipeline itself (`cli/run.py`) is exercised through its unit-tested building blocks rather than
end-to-end against the real dataset, since the dataset can't ship with the repo; `--max-scenes 1` gives a
fast manual smoke check once you have the data locally.

## Deployment

See **[docs/architecture.md#deployment](docs/architecture.md#deployment)** for the full discussion. Short
version: `docker/Dockerfile` has two targets — `cli` (the pipeline, meant to run as a scheduled batch
job / CronJob) and `api` (the same captioning logic behind `/describe`, for on-demand use). Both are built
and pushed to `ghcr.io` in [`.github/workflows/docker.yml`](.github/workflows/docker.yml).

## Development

```bash
just run        # run the pipeline
just dev         # API dev server with hot reload (optional deployment mode)
just test        # unit + integration tests
just fmt          # auto-fix and reformat
just typecheck    # type check
just docs         # build docs
```

See [docs/development.md](docs/development.md) for the full task list and [AGENTS.md](AGENTS.md) for
codebase conventions.

## Docker

```bash
# Run the pipeline (primary deliverable)
docker compose --profile cli run --rm cli

# Optional HTTP API
docker compose up api --build
```

## Configuration

All settings are read from environment variables (or `.env`), prefixed `VLM_SCENE_DESCRIPTION_`. See
[.env.example](.env.example) and [docs/getting-started.md#configuration](docs/getting-started.md#configuration).

## License

See [LICENSE](LICENSE).
