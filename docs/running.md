# Running it

There are several ways to run the project. They all run the same code and read the same `BACKSEAT_DRIVER_*` settings; they differ in *where* the pieces run.

| I want to… | Command | Runs on | Needs |
|---|---|---|---|
| Describe the dataset once | `just run` (= `uv run backseat-driver run`) | host | dataset in `data/` |
| …in a container instead | `just docker-run` (= `docker compose --profile cli run --rm cli run`) | Docker | dataset in `data/` |
| Debug the API locally | `just dev` (`fastapi dev`, no Docker) | host | nothing for `/describe`; RabbitMQ + Postgres for `/ready` and `/jobs` |
| …with `/ready` and `/jobs` working | `just infra`, then `just dev` | API on host, RabbitMQ + Postgres in Docker | Docker |
| Run the API like production, on the host | `just serve` (starts infra first) | same | Docker |
| Run the queue workers on the host | `just worker-ingest` / `just worker-caption` (start infra first) | same | Docker, dataset |
| The whole distributed stack | `just up` (`just up-dev` hot-reloads the API) | Docker Compose | Docker, dataset |
| The same stack in a cluster | `just k8s-apply` | Kubernetes | cluster, dataset volume |

`just --list` shows every recipe; the per-recipe comments say what each needs.

## How the pieces relate

```
just run ─────────────┐
just docker-run ──────┼─▶ backseat-driver run          (batch: loader → captioner → output/*.json)
k8s CronJob `pipeline`┘

just dev / just serve ─┐
compose / k8s `api` ───┴─▶ fastapi app ──▶ RabbitMQ ──▶ ingest / caption workers ──▶ Postgres
                           (/describe is synchronous; /jobs and /ready need RabbitMQ and Postgres)
```

- **One image, two targets.** `docker/Dockerfile` builds `cli` (the pipeline, `db init` and the workers; entrypoint `backseat-driver`) and `api` (`fastapi run`). Compose builds them locally; CI pushes them to `ghcr.io/shoham-b/backseat-driver-{cli,api}`, which the Kubernetes manifests pull.
- **`/ready` needs infrastructure.** The API checks RabbitMQ and Postgres, so an API started without them reports not-ready and the smoke/system tests fail. `just infra` (run for you by `just serve` and `just worker-*`, but not by `just dev`) starts both in Docker, publishes them on `127.0.0.1:5672` / `5432` (the defaults in `.env.example`) and creates the schema.
- **Containers don't read `.env`.** Its `localhost` URLs would be wrong inside a container. Compose instead interpolates the captioner settings (`BACKSEAT_DRIVER_VLM_BACKEND`, model names, `ANTHROPIC_API_KEY`, …) from your shell or `.env`, so `BACKSEAT_DRIVER_VLM_BACKEND=ollama just up` and a `.env` entry behave the same. Broker and database URLs always point at the compose services.
- **Ollama on the host.** Containers reach it at `host.docker.internal:11434`; override with `BACKSEAT_DRIVER_COMPOSE_OLLAMA_URL`.
- **Model weights are cached** in the `hf-cache` volume, so repeat runs don't re-download them.
- **The dataset is never baked into an image.** Compose bind-mounts `./data` read-only; Kubernetes mounts the `nuscenes-data` claim. Queue messages carry image *paths*, so every worker must see the same files at the same path.

## Docker Compose

```bash
just docker-run --max-scenes 2   # one-off pipeline run, writes ./output
just up                          # api :8080, rabbitmq UI :15672, postgres, db-init, ingest-worker, 2 × caption-worker
docker compose up --scale caption-worker=4
just test-compose                # builds, starts the stack, runs system + smoke tests, tears down
```

## Kubernetes

`k8s/` is a kustomize base (namespace `backseat-driver`) with the same topology as compose: Postgres and RabbitMQ StatefulSets, a `db-init` Job, the `api` Deployment and Service, `ingest-worker` and `caption-worker` Deployments, and a suspended `pipeline` CronJob for the batch run.

Before the first `just k8s-apply`:

1. **Dataset volume.** `nuscenes-data` (in `workers.yaml`) is a `ReadWriteMany` claim. Provision storage for it, copy `v1.0-mini` into `data/sets/nuscenes` on it, or edit the claim to point at what you already have.
2. **Secrets.** `config.yaml` ships the same demo credentials as compose. Replace them, and add `BACKSEAT_DRIVER_ANTHROPIC_API_KEY` if you use the `anthropic` backend.
3. **Backend.** Change `BACKSEAT_DRIVER_VLM_BACKEND` and friends in the ConfigMap.

```bash
just k8s-render                                   # inspect first
just k8s-apply
kubectl -n backseat-driver port-forward svc/api 8080:8080
API_URL=http://127.0.0.1:8080 just test-smoke
kubectl -n backseat-driver create job --from=cronjob/pipeline pipeline-manual   # the batch run
```

Not covered yet: ingress, autoscaling (KEDA on queue depth, see [Distributed mode](distributed.md)), and a managed Postgres/RabbitMQ.
