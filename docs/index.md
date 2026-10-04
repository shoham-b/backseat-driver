# Backseat Driver

A production-shaped service for vision-language model (VLM) inference: it describes images in natural language, with the model and runtime (HuggingFace, Ollama, Claude) swappable behind one interface. The nuScenes driving dataset is the demo input that shows the pipeline running end to end; nothing in the design is specific to it.

Backseat Driver is one idea: **read** the scenes, **process** each image with a vision-language model, **write** the descriptions. `describe` runs it in one process, and that is the whole program. The same three steps can also run as tasks over a queue: in one process for local development (`just dev`, no broker, bucket or database), or as separate services where RabbitMQ sits between read and process, the dataset lives in S3 and the results in Postgres. Showing the results (`report`, `ui`) is a separate role that only reads what was written. See [From pipeline to cluster](ladder.md) for the three rungs and where each piece enters the code, and [Running it](running.md) for how to start each.

## Quick start

```bash
uv sync --group dev
uv run pre-commit install

# Run the pipeline; the nuScenes v1.0-mini demo dataset and the model are downloaded on first use:
just describe --camera front --model Salesforce/blip-image-captioning-base
```

Results are written to `output/<backend>__<model>.json` by default, so runs of different models sit side by side and never overwrite each other.

See [Getting Started](getting-started.md) for dataset setup, Docker usage, and the optional HTTP API, or run `just --list` to see all available dev tasks.

See [Running it](running.md) for how the CLI, `just`, Docker, Compose, Kubernetes and the API dev/production servers fit together.

See [From pipeline to cluster](ladder.md) for how the one pipeline grows into a cluster, [Technology](technology.md) for the tech stack, and [Design Decisions](design-decisions.md) for the alternatives considered and why each was (or wasn't) chosen.

See [Distributed mode](distributed.md) for the optional API + queue + worker deployment built around the same pipeline.

See [Deployment](deployment.md) for the Docker images, Compose profiles, Kubernetes manifests and the release checklist.
