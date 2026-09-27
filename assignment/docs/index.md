# VLM Scene Description

Generates short natural-language scene descriptions for nuScenes driving scenes using a vision-language model.

## Quick start

```bash
uv sync --group dev
uv run pre-commit install

# Download the nuScenes v1.0-mini dataset into data/sets/nuscenes (see Getting Started),
# then run the pipeline:
just run
```

Results are written to `output/scene_descriptions.json` by default.

See [Getting Started](getting-started.md) for dataset setup, Docker usage, and the optional HTTP API, or run `just --list` to see all available dev tasks.
