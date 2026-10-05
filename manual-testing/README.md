# Manual testing

Everything that can run in CI does (see `.github/workflows/ci.yml`). This folder holds only what cannot: it needs the
real nuScenes dataset, a real model, a real cluster, or a human looking at the result. It is deliberately **not** part
of the published MkDocs site.

Before adding a step here, ask whether a CI job could do it. If yes, put it in CI; if a step later becomes automatable,
move it out of this folder.

## What CI already covers (do not repeat by hand)

| Area | Where |
|---|---|
| Lint, format, types | `lint`, `typecheck` jobs |
| Unit + integration tests, API fuzzing, layering and import-cost rules | `test` (Linux) and `test-windows` jobs |
| Report UI behaviour in headless Chrome | `test-ui` job |
| Built wheel installs into an empty environment, CLI starts, every extra resolves | `package` job |
| Compose stack end to end (API, broker, database, workers, real BLIP model) | `test-system` job |
| Kubernetes base on kind with KEDA: probes, workers, autoscaling up and down | `kind` job |
| Pods start non-root with all capabilities dropped; the API with a read-only root filesystem | `kind` job (the manifests' `securityContext`) and `test_deployment.py` |
| Manifests and compose file validate against their schemas | `deploy-config` job |
| Docs build strictly: no broken links, nav entries or unrenderable docstrings | `docs` job |
| Benchmarks on synthetic data | `codspeed` workflow |

## What stays manual, and why

| Check | Why CI cannot do it | Guide |
|---|---|---|
| Real nuScenes data and caption quality | The dataset needs a licence acceptance and cannot be redistributed; CI uses a synthetic dataset and a stub or small model, and no test can judge whether a caption is *good* | [real-run.md](real-run.md) |
| Documentation is true and followable | CI builds the site `--strict` (links, nav, docstrings) but cannot judge accuracy or whether a newcomer can follow it | [docs.md](docs.md) |
| Report appearance | Selenium checks behaviour, not whether the page looks right | [report-ui.md](report-ui.md) |
| Production overlay on a real cluster | Needs managed Postgres, RabbitMQ, a real S3 bucket, secrets, an ingress controller and a CNI that enforces NetworkPolicy | [production-cluster.md](production-cluster.md) |
| Throughput on real data and hardware | CI runners are shared and have no GPU, and the real dataset is not available there | [performance.md](performance.md) |

## When to run what

| Situation | Run |
|---|---|
| Before tagging a release | everything, in the order of the table above |
| Changed the loader, the nuScenes reader or the image path | [real-run.md](real-run.md) |
| Changed the captioning backends, batching or prompts | [real-run.md](real-run.md) and [performance.md](performance.md) |
| Changed a command, option, setting or anything the docs describe | [docs.md](docs.md) |
| Changed `report_template.html` or the report metrics | [report-ui.md](report-ui.md) |
| Changed `deploy/production` or the Dockerfile | [production-cluster.md](production-cluster.md) |

Note anything you find wrong as an issue, and say which guide step caught it, so the step can be turned into a test if
it ever can be.
