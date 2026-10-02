# Backseat Driver

Generates short natural-language scene descriptions for nuScenes driving scenes using a vision-language model.

## Quick start

```bash
uv sync --group dev
uv run pre-commit install

# Download the nuScenes v1.0-mini dataset into data/sets/nuscenes (see Getting Started),
# then run the pipeline:
just run
```

Results are written to `output/<backend>__<model>.json` by default, so runs of different models sit side by side and never overwrite each other.

See [Getting Started](getting-started.md) for dataset setup, Docker usage, and the optional HTTP API, or run `just --list` to see all available dev tasks.

See [Running it](running.md) for how the CLI, `just`, Docker, Compose, Kubernetes and the API dev/production servers fit together.

See [Architecture](architecture.md) for the tech stack and object model, and [Design Decisions](design-decisions.md) for the alternatives considered and why each was (or wasn't) chosen.

See [Distributed mode](distributed.md) for the optional API + queue + worker deployment built around the same pipeline.
