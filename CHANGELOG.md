# Changelog

All notable changes to Backseat Driver will be documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- `datasets/` package: the distributed workers read the nuScenes dataset from an S3-compatible bucket (`BACKSEAT_DRIVER_DATASET_BUCKET`, `BACKSEAT_DRIVER_S3_ENDPOINT_URL`, `AWS_*` credentials) instead of a shared volume. `ImageStore` / `DatasetStore` ports with local and S3 adapters, `StoredSceneLoader` (ingest reads only the metadata tables) and `CaptionTask.image_uri`
- `dataset upload` CLI command and a `dataset-upload` compose service / Kubernetes Job: the one-time copy of the dataset into the bucket
- `worker ingest --once` and a KEDA `ScaledJob` that runs ingest as a Job per queued task
- `GET /images/{key}` on the API and `report`/`ui --job <id>`: the report UI reads a finished job's descriptions and images from the API alone. In the monolith too, `image_path` of a job's descriptions is now the dataset-relative key (`LocalImageStore` is rooted at the dataroot)
- `GET /jobs` on the API and `BACKSEAT_DRIVER_UI_ALL_JOBS` for the UI (a FastAPI app run with `fastapi run`, `just ui`; there is no `ui` CLI command): the report UI discovers the completed jobs itself, re-reads them on every page load and proxies the images from the API, so the deployed `ui` mounts no volume
- The monolith keeps its jobs in a SQLite file (`BACKSEAT_DRIVER_JOBS_DB_PATH`, default `output/jobs.db`), so job ids and results survive a restart
- Development S3 store (`adobe/s3mock`) in docker compose, `just infra` and the Kubernetes base
- Design Decisions 7-16: where the monolith keeps its jobs, why two workers, how data is passed, how the dataset reaches them, why ingest is a Job, and how the report UI reads from the API
- `report` CLI command: builds a self-contained HTML page comparing how each model described every scene, with scene/model/text filters and precision/recall/F1 against the nuScenes scene label
- `reference_description` on `SceneKeyframe`/`SceneDescription`, filled from the nuScenes scene description

### Changed

- Distributed mode: no worker mounts the dataset any more; `describe_keyframe` takes the path to caption explicitly; `CaptionTask` has a required `image_uri`, so messages queued by the previous version are rejected
- A distributed API now builds the dataset store at startup and refuses to start without `BACKSEAT_DRIVER_DATASET_BUCKET`; the `api` image includes the S3 client
- `PostgresJobStore` is now `SqlJobStore` (it also runs over SQLite); `JobStore` gained `list_jobs`
- Celery tasks are registered per app (`shared=False`), so `register_tasks` no longer leaks tasks into other apps

## [0.1.0] — Initial release

### Added

- nuScenes scene loader, BLIP captioner, and pipeline that writes scene descriptions as JSON
- `run` CLI command for the full pipeline
- Optional FastAPI `/describe` endpoint and distributed job mode (Celery, RabbitMQ, Postgres)
