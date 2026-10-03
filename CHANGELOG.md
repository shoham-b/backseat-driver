# Changelog

All notable changes to Backseat Driver will be documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project adheres to [Semantic Versioning](https://semver.org/).

## [0.2.0](https://github.com/shoham-b/backseat-driver/compare/v0.1.0...v0.2.0) (2026-10-03)


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
* download nuScenes into a self-validating cache dir ([#42](https://github.com/shoham-b/backseat-driver/issues/42)) ([1b4eaf4](https://github.com/shoham-b/backseat-driver/commit/1b4eaf45b5dda616573559c9c5ab3039d3fbc32f))
* HTML report comparing model descriptions per scene, with accuracy metrics ([#33](https://github.com/shoham-b/backseat-driver/issues/33)) ([8d06b59](https://github.com/shoham-b/backseat-driver/commit/8d06b5989e8dff0c6b8f95cf01a1968df73a734e))
* implement the nuScenes VLM scene-description pipeline ([00a014b](https://github.com/shoham-b/backseat-driver/commit/00a014b464eb7334634fbeaae9c0666bacecbd0d))
* live picture inference card in the report UI ([#39](https://github.com/shoham-b/backseat-driver/issues/39)) ([77f454a](https://github.com/shoham-b/backseat-driver/commit/77f454a2621d5c022428ed98ecd17a9903505cc8))
* monolith dev mode, per-service images, local Kubernetes with autoscaling ([#34](https://github.com/shoham-b/backseat-driver/issues/34)) ([15c4099](https://github.com/shoham-b/backseat-driver/commit/15c409954191f83af5bf6750f4714171466bdf88))


### Bug Fixes

* attribute intercepted stdlib log records to their real caller ([#57](https://github.com/shoham-b/backseat-driver/issues/57)) ([86d5a50](https://github.com/shoham-b/backseat-driver/commit/86d5a50b2fad56cfb78773dda67cf495941de4be))
* **ci:** replace runner.workspace in codeql SARIF upload path ([95ccefe](https://github.com/shoham-b/backseat-driver/commit/95ccefe3de39d9feccefab00ec3b68ca3cd53c13))
* **ci:** replace runner.workspace in codeql workflow ([aeb3ace](https://github.com/shoham-b/backseat-driver/commit/aeb3ace7f66e5caa9cae6048303453f11c8919ba))
* **ci:** write CodeQL SARIF inside workspace ([71fadac](https://github.com/shoham-b/backseat-driver/commit/71fadacc1e50007c954a80ad321848b001feab34))
* **ci:** write CodeQL SARIF inside workspace so upload-artifact accepts the path ([b70f1f2](https://github.com/shoham-b/backseat-driver/commit/b70f1f2b256c241d0f845a3cbfd6c7bac07ceabb))
* derive CORS origins from the UI host and port ([#54](https://github.com/shoham-b/backseat-driver/issues/54)) ([6753d23](https://github.com/shoham-b/backseat-driver/commit/6753d23ceea83918e76ba8853bb612f9fa01beb7))
* implement BlipCaptioner, NuScenesSceneLoader and write_json leaf functions ([4e1c797](https://github.com/shoham-b/backseat-driver/commit/4e1c79776ae4555cdc452478ab4026fa79912a12))
* implement captioner, nuScenes loader and JSON writer stubs ([9b07fce](https://github.com/shoham-b/backseat-driver/commit/9b07fcef845faf592e72892b8c003f243548334e))


### Documentation

* fix badge and repo URLs after rename ([4fd44e0](https://github.com/shoham-b/backseat-driver/commit/4fd44e07422171eb6f5e3d2320f37e28b01b353c))
* fix badge and repo URLs after rename to backseat-driver ([fc04a64](https://github.com/shoham-b/backseat-driver/commit/fc04a649c6d2b1062aae3fb8bc9d28dba827dff0))
* replace scaffold changelog entry with real feature list ([6294556](https://github.com/shoham-b/backseat-driver/commit/62945564c5c3bf3e7c3a877146a11edc972b2d22))
* replace scaffold changelog entry with real feature list ([c4aff7e](https://github.com/shoham-b/backseat-driver/commit/c4aff7efa4b1b76ef2385add37c5ef55c5866316))
* scope unit tests to a single unit and cover workers in integration tests ([#46](https://github.com/shoham-b/backseat-driver/issues/46)) ([07566c0](https://github.com/shoham-b/backseat-driver/commit/07566c0cb4e4fe1c29022d3fcb64427a38bed930))
* tighten comment rule and require replying to every PR review comment ([#58](https://github.com/shoham-b/backseat-driver/issues/58)) ([17f8cff](https://github.com/shoham-b/backseat-driver/commit/17f8cff303bb492cbd35ca4e7203a5a6e7b093a3))


### Code Refactoring

* rename package to backseat-driver ([37513a6](https://github.com/shoham-b/backseat-driver/commit/37513a6db825c181f9b7252b685f49e8fe811762))

## [Unreleased]

### Added

- `report` CLI command: builds a self-contained HTML page comparing how each model described every scene, with scene/model/text filters and precision/recall/F1 against the nuScenes scene label
- `reference_description` on `SceneKeyframe`/`SceneDescription`, filled from the nuScenes scene description

## [0.1.0] — Initial release

### Added

- nuScenes scene loader, BLIP captioner, and pipeline that writes scene descriptions as JSON
- `run` CLI command for the full pipeline
- Optional FastAPI `/describe` endpoint and distributed job mode (Celery, RabbitMQ, Postgres)
