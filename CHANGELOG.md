# Changelog

All notable changes to Backseat Driver will be documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- `worker ingest --once` and a KEDA `ScaledJob` that runs ingest as a Job per queued task
- `datasets/` package: the distributed workers read the nuScenes dataset from an S3-compatible bucket (`BACKSEAT_DRIVER_DATASET_BUCKET`, `BACKSEAT_DRIVER_S3_ENDPOINT_URL`, `AWS_*` credentials) instead of a shared volume. `ImageStore` / `DatasetStore` ports with local and S3 adapters, `StoredSceneLoader` (ingest reads only the metadata tables) and `CaptionTask.image_uri`
- `dataset upload` CLI command and a `dataset-upload` compose service / Kubernetes Job: the one-time copy of the dataset into the bucket
- Development S3 store (`adobe/s3mock`) in docker compose, `just infra` and the Kubernetes base
- A distributed `Settings` cannot be built without `BACKSEAT_DRIVER_DATASET_BUCKET`
- `GET /jobs` on the API: the jobs newest first, optionally only those in one `state`, capped by `limit`
- The monolith keeps its jobs in a SQLite file (`BACKSEAT_DRIVER_JOBS_DB_PATH`, default `output/jobs.db`), so job ids and results survive a restart. Empty keeps them in memory
- `report` CLI command: builds a self-contained HTML page comparing how each model described every scene, with scene/model/text filters and precision/recall/F1 against the nuScenes scene label
- `reference_description` on `SceneKeyframe`/`SceneDescription`, filled from the nuScenes scene description

### Changed

- Distributed mode: no worker mounts the dataset any more; `describe_keyframe` takes the path to caption explicitly; `CaptionTask` has a required `image_uri`, so messages queued by the previous version are rejected
- A job's `image_path` is now the dataset-relative key (`samples/CAM_FRONT/<name>.jpg`) in the monolith too (`LocalImageStore` is rooted at the dataroot)
- Celery tasks are registered per app (`shared=False`), so `register_tasks` no longer leaks tasks into other apps
- `PostgresJobStore` is now `SqlJobStore` (it also runs over SQLite); `JobStore` gained `list_jobs`

## [0.1.0] — Initial release

### Added

- nuScenes scene loader, BLIP captioner, and pipeline that writes scene descriptions as JSON
- `run` CLI command for the full pipeline
- Optional FastAPI `/describe` endpoint and distributed job mode (Celery, RabbitMQ, Postgres)
