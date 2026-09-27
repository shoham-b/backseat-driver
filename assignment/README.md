# VLM Scene Description

![Python Version](https://img.shields.io/badge/python-3.13-blue?logo=python&logoColor=white)
![Tests Status](https://github.com/shoham-b/vlm_scene_description/actions/workflows/ci.yml/badge.svg)
![Docker Build](https://github.com/shoham-b/vlm_scene_description/actions/workflows/docker.yml/badge.svg)
![CodeQL](https://github.com/shoham-b/vlm_scene_description/actions/workflows/codeql.yml/badge.svg)
[![codecov](https://codecov.io/gh/shoham-b/vlm_scene_description/graph/badge.svg)](https://codecov.io/gh/shoham-b/vlm_scene_description)
[![Docs](https://img.shields.io/badge/docs-github--pages-blue)](https://shoham-b.github.io/vlm_scene_description/)
[![Generated from python-project-template](https://img.shields.io/badge/generated%20from-python--project--template-8A2BE2)](https://github.com/shoham-b/python-project-template)

Generates short natural-language scene descriptions for nuScenes driving scenes using a vision-language model

## Documentation

Full documentation is available at **https://shoham-b.github.io/vlm_scene_description/**.

## Requirements

- Python 3.13+
- [uv](https://docs.astral.sh/uv/)

## Quickstart

```bash
uv sync --group dev
uv run pre-commit install
```

## Development

```bash
# Run dev server with auto-reload
just dev

# Run tests
just test

# Lint and format
just fmt

# Type check
just typecheck

# Build docs
just docs
```

## Docker

```bash
# Build and start all services
docker compose up --build

# Dev compose with hot-reload mounts
docker compose -f docker-compose.dev.yml up
```

## Testing

| Command | Scope |
|---|---|
| `just test` | Unit + integration |
| `just test-smoke` | Smoke tests against a live API |
| `just test-system` | Full system tests (auto-starts service) |
| `just test-all` | Everything except smoke |

## Configuration

All settings are read from environment variables (or `.env`). See `.env.example` for available options.

## License

See [LICENSE](LICENSE).
