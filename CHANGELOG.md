# Changelog

All notable changes to VLM Scene Description will be documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.0] — Initial release

### Added

- nuScenes scene loader, BLIP captioner, and pipeline that writes scene descriptions as JSON
- `run` CLI command for the full pipeline
- Optional FastAPI `/describe` endpoint and distributed job mode (Celery, RabbitMQ, Postgres)
