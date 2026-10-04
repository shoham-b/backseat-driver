# Backseat Driver

A production-shaped service for vision-language model (VLM) inference: it describes images in natural language, with the model and runtime (HuggingFace, Ollama, Claude) swappable behind one interface. The nuScenes driving dataset is the demo input that shows the pipeline running end to end; nothing in the design is specific to it.

Backseat Driver is a **monorepo of microservices**: the API, the ingest and caption workers, the report UI and the batch CLI live in one Python package and are built into one image per service. The same code can also be **debugged as a monolith**: one process runs the API and both workers together, with an in-process queue and a SQLite (or in-memory) job store. Debugging as a monolith drops RabbitMQ, S3 and Postgres, so `just dev` needs nothing but the API. See [Distributed mode](distributed.md) for the microservices and [Running it](running.md) for how to start either.

## Quick start

```bash
uv sync --group dev
uv run pre-commit install

# Run the pipeline; the nuScenes v1.0-mini demo dataset and the model are downloaded on first use:
just run --camera front --model Salesforce/blip-image-captioning-base
```

Results are written to `output/<backend>__<model>.json` by default, so runs of different models sit side by side and never overwrite each other.

See [Getting Started](getting-started.md) for dataset setup, Docker usage, and the optional HTTP API, or run `just --list` to see all available dev tasks.

See [Running it](running.md) for how the CLI, `just`, Docker, Compose, Kubernetes and the API dev/production servers fit together.

See [Architecture](architecture.md) for the tech stack and object model, and [Design Decisions](design-decisions.md) for the alternatives considered and why each was (or wasn't) chosen.

See [Distributed mode](distributed.md) for the optional API + queue + worker deployment built around the same pipeline.

See [Deployment](deployment.md) for the Docker images, Compose profiles, Kubernetes manifests and the release checklist.
