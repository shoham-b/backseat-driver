# Changelog

All notable changes to Backseat Driver will be documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- `report` CLI command: builds a self-contained HTML page comparing how each model described every scene, with scene/model/text filters and precision/recall/F1 against the nuScenes scene label
- `reference_description` on `SceneKeyframe`/`SceneDescription`, filled from the nuScenes scene description

## [0.1.0] — Initial release

### Added

- nuScenes scene loader, BLIP captioner, and pipeline that writes scene descriptions as JSON
- `run` CLI command for the full pipeline
- Optional FastAPI `/describe` endpoint and distributed job mode (Celery, RabbitMQ, Postgres)
