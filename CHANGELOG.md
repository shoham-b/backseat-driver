# Changelog

All notable changes to Backseat Driver will be documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project adheres to [Semantic Versioning](https://semver.org/).

## [0.2.4](https://github.com/shoham-b/backseat-driver/compare/v0.2.3...v0.2.4) (2026-10-05)


### Bug Fixes

* cancel the other Anthropic requests when one fails ([#143](https://github.com/shoham-b/backseat-driver/issues/143)) ([ece71c7](https://github.com/shoham-b/backseat-driver/commit/ece71c7a3bf6ccb3ed0afeaef37f975273266017))
* run one thread at a time inside the local caption model ([#147](https://github.com/shoham-b/backseat-driver/issues/147)) ([df1e45b](https://github.com/shoham-b/backseat-driver/commit/df1e45b8dea94fc04789a78c8d70cdbe5189046f))


### Performance Improvements

* batch captioning, overlap startup, lean nuScenes table reader ([#136](https://github.com/shoham-b/backseat-driver/issues/136)) ([a9a4a74](https://github.com/shoham-b/backseat-driver/commit/a9a4a74c8c4ad9aef414f62e03961dc8528d68c3))

## [0.2.3](https://github.com/shoham-b/backseat-driver/compare/v0.2.2...v0.2.3) (2026-10-05)


### Bug Fixes

* declare the runtime dependencies in the wheel as dependencies and extras ([#135](https://github.com/shoham-b/backseat-driver/issues/135)) ([c38cdcb](https://github.com/shoham-b/backseat-driver/commit/c38cdcbb6260b57942afd9a8a55111288419cacf))


### Documentation

* state the scope in the README, trim AGENTS.md, drop file paths from comments ([#132](https://github.com/shoham-b/backseat-driver/issues/132)) ([d92e1b7](https://github.com/shoham-b/backseat-driver/commit/d92e1b75e76d4e14f3cb208355ee6c39471d57c0))

## [0.2.2](https://github.com/shoham-b/backseat-driver/compare/v0.2.1...v0.2.2) (2026-10-05)


### Features

* **deploy:** add a production kustomize overlay ([#106](https://github.com/shoham-b/backseat-driver/issues/106)) ([71581e0](https://github.com/shoham-b/backseat-driver/commit/71581e0be50067e79e6de0516602247bbcc8f891))
* failed jobs, one transaction_id log field, validated ids and idempotent POST /jobs ([#98](https://github.com/shoham-b/backseat-driver/issues/98)) ([3ca34d6](https://github.com/shoham-b/backseat-driver/commit/3ca34d6d5bf33ce1fbaa74611168a5218bcf4868))
* keep tasks that exhaust their retries as dead letters ([#105](https://github.com/shoham-b/backseat-driver/issues/105)) ([7fe1c0e](https://github.com/shoham-b/backseat-driver/commit/7fe1c0ecbd9d5f04764471fb014421499f2371a1))


### Bug Fixes

* cap Ollama generation and fail fast when it hits the limit ([#111](https://github.com/shoham-b/backseat-driver/issues/111)) ([117fa4e](https://github.com/shoham-b/backseat-driver/commit/117fa4ee3c8665c9e91afa2ed46c7d7597c6b86b))
* fail fast on an outdated jobs database and make the tests hermetic ([#109](https://github.com/shoham-b/backseat-driver/issues/109)) ([6662334](https://github.com/shoham-b/backseat-driver/commit/6662334026268157d8f76baaa507bce2219b4075))
* give jobs distinct, increasing created_at values so newest-first is well defined ([#126](https://github.com/shoham-b/backseat-driver/issues/126)) ([4c96f8b](https://github.com/shoham-b/backseat-driver/commit/4c96f8be2eb9a6c54f795f247e44b0250d6f96b2))
* key a job's descriptions by camera and count max_scenes in scenes in ingest ([#107](https://github.com/shoham-b/backseat-driver/issues/107)) ([1bfbc46](https://github.com/shoham-b/backseat-driver/commit/1bfbc462709e037e899ae55150274f673cdedf29))
* match BaseHTTPRequestHandler.log_message in the CI Ollama stub ([#117](https://github.com/shoham-b/backseat-driver/issues/117)) ([ebeaeab](https://github.com/shoham-b/backseat-driver/commit/ebeaeabbb819237f13e07fe7f4b8dd3dd10f7fd8))
* one JobStore error per case, so a concurrent duplicate Idempotency-Key no longer 500s ([#114](https://github.com/shoham-b/backseat-driver/issues/114)) ([d264b58](https://github.com/shoham-b/backseat-driver/commit/d264b586642057160ecd136d6a64c673d96ac434))
* probe the captioner in /ready off the event loop ([#120](https://github.com/shoham-b/backseat-driver/issues/120)) ([61a5031](https://github.com/shoham-b/backseat-driver/commit/61a50311edb03461108f21d2deb30d1cb610d004))
* reject a database whose tables have another primary key than the code writes with ([#124](https://github.com/shoham-b/backseat-driver/issues/124)) ([744f1be](https://github.com/shoham-b/backseat-driver/commit/744f1becf505ac58a4e15fbd6002dfa603668f93))
* reject a max_scenes below 1 in the CLI, the pipeline and the ingest worker ([#112](https://github.com/shoham-b/backseat-driver/issues/112)) ([d76f8ad](https://github.com/shoham-b/backseat-driver/commit/d76f8adcc4026e05c7a07a1005e5ed8db31915f7))
* report an unreadable /describe image as 422 and any other captioner failure as 500 ([#116](https://github.com/shoham-b/backseat-driver/issues/116)) ([e6a3cd0](https://github.com/shoham-b/backseat-driver/commit/e6a3cd0e04de23311a1a76c5625855a92940407e))
* stop when the nuScenes cache cannot be cleared instead of downloading over it ([#119](https://github.com/shoham-b/backseat-driver/issues/119)) ([647dbf0](https://github.com/shoham-b/backseat-driver/commit/647dbf0f6c813dc360bc6e28a7cd3b343c6e2514))


### Documentation

* fix links, diagrams and stale claims; split architecture into APIs and Technology ([#102](https://github.com/shoham-b/backseat-driver/issues/102)) ([c4a2699](https://github.com/shoham-b/backseat-driver/commit/c4a269990d6f1520a5c10fe45be2fa30e8a55b57))
* rewrite the README to lead with the pitch and mirror the docs ([#104](https://github.com/shoham-b/backseat-driver/issues/104)) ([4bd3ae1](https://github.com/shoham-b/backseat-driver/commit/4bd3ae1f2487e7784313675cd0135908ed2679a0))

## [0.2.1](https://github.com/shoham-b/backseat-driver/compare/v0.2.0...v0.2.1) (2026-10-04)


### Features

* ask Ollama and Claude captioners for one short sentence ([#89](https://github.com/shoham-b/backseat-driver/issues/89)) ([523424b](https://github.com/shoham-b/backseat-driver/commit/523424bd2608489b4334608cd409607c9f8a2d24))
* prompt captioners for a keyword list in the style of the nuScenes labels ([#92](https://github.com/shoham-b/backseat-driver/issues/92)) ([e8d6307](https://github.com/shoham-b/backseat-driver/commit/e8d63072b750d45c3ddbd490b39e45b7abce4363))


### Bug Fixes

* keep the reference label on stored jobs and stem report metrics ([#88](https://github.com/shoham-b/backseat-driver/issues/88)) ([0ce0300](https://github.com/shoham-b/backseat-driver/commit/0ce03003369c443a1ad425dcb4a82f5ce53fa5bf))
* let Ctrl-C interrupt the describe command ([#93](https://github.com/shoham-b/backseat-driver/issues/93)) ([27a57de](https://github.com/shoham-b/backseat-driver/commit/27a57de624acd2052761fb301eadfb0646bc712e))

## [0.2.0](https://github.com/shoham-b/backseat-driver/compare/v0.1.0...v0.2.0) (2026-10-04)


### ⚠ BREAKING CHANGES

* rename package to backseat-driver

### Features

* add bd as a short alias for backseat-driver ([#48](https://github.com/shoham-b/backseat-driver/issues/48)) ([417879e](https://github.com/shoham-b/backseat-driver/commit/417879e676e4a97cb0d2b1739fd311cc5ab987fd))
* add optional distributed mode (API + RabbitMQ + Postgres + workers) ([8081468](https://github.com/shoham-b/backseat-driver/commit/80814687d786958dffd33c41497fa0c37a2b4070))
* add transaction_id correlating API, queue messages, store and worker logs ([8784c1b](https://github.com/shoham-b/backseat-driver/commit/8784c1b0459c8b785dc92774fa25f0f7ba898e8f))
* align CLI, just, Docker, Compose and Kubernetes run paths ([#37](https://github.com/shoham-b/backseat-driver/issues/37)) ([d098d91](https://github.com/shoham-b/backseat-driver/commit/d098d91c354fba0958b5ce25d3285d778237b486))
* deployable on Docker and Kubernetes; fixes from manual testing ([#38](https://github.com/shoham-b/backseat-driver/issues/38)) ([7d5f3ff](https://github.com/shoham-b/backseat-driver/commit/7d5f3ffa62267e77932c898673164dda43f9e753))
* describe several cameras per scene and show the camera in the report ([#55](https://github.com/shoham-b/backseat-driver/issues/55)) ([9deb4cb](https://github.com/shoham-b/backseat-driver/commit/9deb4cb681392750351153cf67dd1a392043393d))
* distributed mode (API + RabbitMQ + Postgres + workers) ([00484ab](https://github.com/shoham-b/backseat-driver/commit/00484ab3c5a50c0b1db4acc74add7344e1811e78))
* distributed workers read the dataset from S3, not a shared volume ([#74](https://github.com/shoham-b/backseat-driver/issues/74)) ([87448e3](https://github.com/shoham-b/backseat-driver/commit/87448e3e0bcd7a0cd59c3b39be7d0b31c5929852))
* download nuScenes into a self-validating cache dir ([#42](https://github.com/shoham-b/backseat-driver/issues/42)) ([1b4eaf4](https://github.com/shoham-b/backseat-driver/commit/1b4eaf45b5dda616573559c9c5ab3039d3fbc32f))
* group cameras per scene and make the report page more interactive ([#71](https://github.com/shoham-b/backseat-driver/issues/71)) ([24898f2](https://github.com/shoham-b/backseat-driver/commit/24898f2de32f3565b9731c7435615df81705e98d))
* HTML report comparing model descriptions per scene, with accuracy metrics ([#33](https://github.com/shoham-b/backseat-driver/issues/33)) ([8d06b59](https://github.com/shoham-b/backseat-driver/commit/8d06b5989e8dff0c6b8f95cf01a1968df73a734e))
* implement the nuScenes VLM scene-description pipeline ([00a014b](https://github.com/shoham-b/backseat-driver/commit/00a014b464eb7334634fbeaae9c0666bacecbd0d))
* live picture inference card in the report UI ([#39](https://github.com/shoham-b/backseat-driver/issues/39)) ([77f454a](https://github.com/shoham-b/backseat-driver/commit/77f454a2621d5c022428ed98ecd17a9903505cc8))
* make --camera a selectable enum in the run CLI ([#79](https://github.com/shoham-b/backseat-driver/issues/79)) ([3686da5](https://github.com/shoham-b/backseat-driver/commit/3686da59d2ed46b27cb71a194c5c0872c6ef1505))
* monolith dev mode, per-service images, local Kubernetes with autoscaling ([#34](https://github.com/shoham-b/backseat-driver/issues/34)) ([15c4099](https://github.com/shoham-b/backseat-driver/commit/15c409954191f83af5bf6750f4714171466bdf88))
* move camera tabs under the scene score ([#78](https://github.com/shoham-b/backseat-driver/issues/78)) ([3b5191d](https://github.com/shoham-b/backseat-driver/commit/3b5191d5a9520a0de4efa7bd14552cf05fc1ed86))
* progress bars in run and more informative logs ([#72](https://github.com/shoham-b/backseat-driver/issues/72)) ([06a87a6](https://github.com/shoham-b/backseat-driver/commit/06a87a62c76e3395532bce265c59ffcfd118521b))
* restyle the model-comparison page ([#70](https://github.com/shoham-b/backseat-driver/issues/70)) ([5afca00](https://github.com/shoham-b/backseat-driver/commit/5afca00cf03666dede6588eb350c1a823b98471b))
* the monolith keeps its jobs in a SQLite file; add GET /jobs ([#73](https://github.com/shoham-b/backseat-driver/issues/73)) ([10752aa](https://github.com/shoham-b/backseat-driver/commit/10752aa87ae6bd5dc72fb1c49ffb778d5a24e668))


### Bug Fixes

* ask Claude for a single short phrase when captioning ([#81](https://github.com/shoham-b/backseat-driver/issues/81)) ([febb0ff](https://github.com/shoham-b/backseat-driver/commit/febb0ff05a1111f36646704361966027b0d49084))
* attribute intercepted stdlib log records to their real caller ([#57](https://github.com/shoham-b/backseat-driver/issues/57)) ([86d5a50](https://github.com/shoham-b/backseat-driver/commit/86d5a50b2fad56cfb78773dda67cf495941de4be))
* **ci:** replace runner.workspace in codeql SARIF upload path ([95ccefe](https://github.com/shoham-b/backseat-driver/commit/95ccefe3de39d9feccefab00ec3b68ca3cd53c13))
* **ci:** replace runner.workspace in codeql workflow ([aeb3ace](https://github.com/shoham-b/backseat-driver/commit/aeb3ace7f66e5caa9cae6048303453f11c8919ba))
* **ci:** write CodeQL SARIF inside workspace ([71fadac](https://github.com/shoham-b/backseat-driver/commit/71fadacc1e50007c954a80ad321848b001feab34))
* **ci:** write CodeQL SARIF inside workspace so upload-artifact accepts the path ([b70f1f2](https://github.com/shoham-b/backseat-driver/commit/b70f1f2b256c241d0f845a3cbfd6c7bac07ceabb))
* derive CORS origins from the UI host and port ([#54](https://github.com/shoham-b/backseat-driver/issues/54)) ([6753d23](https://github.com/shoham-b/backseat-driver/commit/6753d23ceea83918e76ba8853bb612f9fa01beb7))
* implement BlipCaptioner, NuScenesSceneLoader and write_json leaf functions ([4e1c797](https://github.com/shoham-b/backseat-driver/commit/4e1c79776ae4555cdc452478ab4026fa79912a12))
* implement captioner, nuScenes loader and JSON writer stubs ([9b07fce](https://github.com/shoham-b/backseat-driver/commit/9b07fcef845faf592e72892b8c003f243548334e))
* route CLI status, warnings and transformers output through loguru ([#68](https://github.com/shoham-b/backseat-driver/issues/68)) ([d25c6cb](https://github.com/shoham-b/backseat-driver/commit/d25c6cb770aa36bd38cabbf8c3ca8a0fff4425bd))
* run just recipes with Git Bash on Windows, not WSL bash ([#60](https://github.com/shoham-b/backseat-driver/issues/60)) ([16aefa5](https://github.com/shoham-b/backseat-driver/commit/16aefa52d4a47b6a2666ceb30e3b2ef9053cf70e))
* use sh for the Windows just shell instead of a hardcoded path ([#61](https://github.com/shoham-b/backseat-driver/issues/61)) ([83772e1](https://github.com/shoham-b/backseat-driver/commit/83772e1af42a99d272f45081d84379ac343b2b88))
* use Windows PowerShell for just on Windows ([#62](https://github.com/shoham-b/backseat-driver/issues/62)) ([9ceb113](https://github.com/shoham-b/backseat-driver/commit/9ceb11376e8298276a29af71130e6c33814d5ba9))


### Documentation

* fix badge and repo URLs after rename ([4fd44e0](https://github.com/shoham-b/backseat-driver/commit/4fd44e07422171eb6f5e3d2320f37e28b01b353c))
* fix badge and repo URLs after rename to backseat-driver ([fc04a64](https://github.com/shoham-b/backseat-driver/commit/fc04a649c6d2b1062aae3fb8bc9d28dba827dff0))
* frame the project around VLM inference and fix stale README/docs ([#83](https://github.com/shoham-b/backseat-driver/issues/83)) ([ff2a72a](https://github.com/shoham-b/backseat-driver/commit/ff2a72a383d40181e70486439a484d61c3f1b88a))
* link README badges to their workflow runs ([#84](https://github.com/shoham-b/backseat-driver/issues/84)) ([d27f287](https://github.com/shoham-b/backseat-driver/commit/d27f2871ed91e476863ab8309aedec0e13ed9c68))
* link the Docker badge to the GitHub packages page ([#77](https://github.com/shoham-b/backseat-driver/issues/77)) ([f70fee3](https://github.com/shoham-b/backseat-driver/commit/f70fee30bdf7b67ae776a6ede70967fca078ad6b))
* replace scaffold changelog entry with real feature list ([6294556](https://github.com/shoham-b/backseat-driver/commit/62945564c5c3bf3e7c3a877146a11edc972b2d22))
* replace scaffold changelog entry with real feature list ([c4aff7e](https://github.com/shoham-b/backseat-driver/commit/c4aff7efa4b1b76ef2385add37c5ef55c5866316))
* scope unit tests to a single unit and cover workers in integration tests ([#46](https://github.com/shoham-b/backseat-driver/issues/46)) ([07566c0](https://github.com/shoham-b/backseat-driver/commit/07566c0cb4e4fe1c29022d3fcb64427a38bed930))
* tighten comment rule and require replying to every PR review comment ([#58](https://github.com/shoham-b/backseat-driver/issues/58)) ([17f8cff](https://github.com/shoham-b/backseat-driver/commit/17f8cff303bb492cbd35ca4e7203a5a6e7b093a3))
* unit test logic, keep adapters thin ([#65](https://github.com/shoham-b/backseat-driver/issues/65)) ([1e4d9f9](https://github.com/shoham-b/backseat-driver/commit/1e4d9f9b74379d56579c507bb7c698cfdeec3a20))


### Code Refactoring

* rename package to backseat-driver ([37513a6](https://github.com/shoham-b/backseat-driver/commit/37513a6db825c181f9b7252b685f49e8fe811762))

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

- `scene_descriptions` has a nullable `reference_description` column, so a job's descriptions keep the nuScenes label and the report UI scores them (`report --job`, `ALL_JOBS`). `db init` does not alter an existing table: add the column (`ALTER TABLE scene_descriptions ADD COLUMN reference_description VARCHAR`) or recreate the database; the monolith's `output/jobs.db` can simply be deleted
- Report metrics stem words (`-ing`, `-ed`, plurals, `buses`/`lorries`) and ignore caption boilerplate ("the image shows"), so "turning left" matches the label's "turn left" and verbose models are no longer penalised for their phrasing; scores differ from earlier reports
- Distributed mode: no worker mounts the dataset any more; `describe_keyframe` takes the path to caption explicitly; `CaptionTask` has a required `image_uri`, so messages queued by the previous version are rejected
- A distributed API now builds the dataset store at startup and refuses to start without `BACKSEAT_DRIVER_DATASET_BUCKET`; the `api` image includes the S3 client
- `PostgresJobStore` is now `SqlJobStore` (it also runs over SQLite); `JobStore` gained `list_jobs`
- Celery tasks are registered per app (`shared=False`), so `register_tasks` no longer leaks tasks into other apps

## [0.1.0] — Initial release

### Added

- nuScenes scene loader, BLIP captioner, and pipeline that writes scene descriptions as JSON
- `run` CLI command for the full pipeline
- Optional FastAPI `/describe` endpoint and distributed job mode (Celery, RabbitMQ, Postgres)
