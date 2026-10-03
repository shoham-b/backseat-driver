# Deployment

Everything below was exercised by hand before release (see [Release checklist](#release-checklist)); the parts that
can be checked without a cluster or a daemon are also pinned by `tests/unittests/test_deployment.py`.

## Images

`docker/Dockerfile` has one runtime target per service, all running as the unprivileged user `app` (uid 10001):

| Target | Entrypoint | Used for |
|---|---|---|
| `cli` | `backseat-driver` | the batch pipeline, the report UI, `db init` |
| `api` | `fastapi run …` on port 8080 | `/describe`, `/jobs`, `/health`, `/ready` |
| `ingest-worker` | `backseat-driver worker ingest` | reads the dataset, fans out caption tasks (nuscenes-devkit, no torch) |
| `caption-worker` | `backseat-driver worker caption` | runs the VLM on one scene at a time (torch, no nuscenes-devkit) |

Model weights are cached under `HF_HOME` (`/home/app/.cache/huggingface`); mount a volume there to survive restarts.
`.github/workflows/docker.yml` publishes them as `ghcr.io/shoham-b/backseat-driver-{cli,api,ingest-worker,caption-worker}:latest`.

## Docker Compose

| Goal | Command |
|---|---|
| Batch run → `./output/*.json` | `just compose --profile cli run --rm cli` |
| Model-comparison UI on <http://localhost:8081> | `just compose --profile ui up ui` |
| API + RabbitMQ + Postgres + workers | `just compose up --build` (API on <http://localhost:8080>) |
| Containerised system + smoke tests | `just test-compose` |

The dataset is read from `./data` and results are written to `./output`. Because the image is non-root, a bind-mounted
`./output` that Docker created as root is not writable; either `mkdir output` and run with
`LOCAL_UID=$(id -u) LOCAL_GID=$(id -g)`, or leave both unset to run as root as before.

The `ui` service exits at startup when `./output` has no result files yet — run the pipeline first.

## Kubernetes

`deploy/k8s` is a Kustomize base (`kubectl apply -k deploy/k8s`) that creates the `backseat-driver` namespace and:

| Object | Notes |
|---|---|
| `api` Deployment (2) + Service | liveness `/health`, readiness `/ready` (VLM, broker and database reachable) |
| `ingest-worker` (1), `caption-worker` (2) | each from its own image; `kubectl -n backseat-driver scale deploy/caption-worker --replicas=N`, or autoscale (below) |
| `db-init` Job | creates the tables; the API and workers recover on their own once it has succeeded |
| `postgres` StatefulSet, `rabbitmq` Deployment | evaluation-grade; point `BACKSEAT_DRIVER_DATABASE_URL` / `_RABBITMQ_URL` at managed services in production |
| `ui` Deployment + Service | the model-comparison report over the `results` volume |
| `nuscenes-data`, `results` PVCs | the dataset (read-only everywhere) and the result JSON files |

```bash
kubectl apply -k deploy/k8s
# nuScenes can't be redistributed: copy data/sets/nuscenes into the nuscenes-data volume, e.g. with a throwaway pod.
kubectl apply -f deploy/k8s/examples/run-job.yaml     # batch run -> results volume
kubectl -n backseat-driver port-forward svc/api 8080:80
kubectl -n backseat-driver port-forward svc/ui 8081:80
```

The config sets `BACKSEAT_DRIVER_MODE=distributed`. Without it the API would use its default monolith mode and run `/jobs`
inside the API pods, never touching the workers.

Before using it for real, replace the development credentials in `config.yaml` (the `Secret` and the RabbitMQ URL) and
pin the image tags with the `images:` block in `kustomization.yaml`. Both PVCs are `ReadWriteOnce`: on a multi-node
cluster either use a `ReadWriteMany` storage class or pin the pods that share a volume to one node.

## Autoscaling and the local kind cluster

`deploy/components/keda-autoscaling` is an optional kustomize component that scales the workers on RabbitMQ queue depth
with [KEDA](https://keda.sh). Queue length measures pending work directly, whereas a solo-pool worker's CPU says little
about how far behind it is. It needs KEDA in the cluster and a `rabbitmq-management` Secret (key `host`: the management API
URL with credentials) from the overlay that uses it.

| Deployment | Queue | Scale | Replicas |
|---|---|---|---|
| `caption-worker` | `backseat_driver.caption` | 1 per 20 waiting scenes | 1–8 |
| `ingest-worker` | `backseat_driver.ingest` | 1 per 2 waiting jobs | 1–3 |

The minimum is 1, not 0: a new caption replica loads the model before consuming, and scaling to zero would add that to
the first job. Scaling down is safe because acks are late: a replica removed mid-caption has its message redelivered, and
the write is idempotent. The component removes `replicas` from the worker Deployments so re-applying never resets the
autoscaler's count. The API is not autoscaled (that would need metrics-server).

`deploy/kind` is a ready-made overlay for a local [kind](https://kind.sigs.k8s.io/) cluster that uses the component:

```bash
just k8s-up       # cluster + images + KEDA + deploy; the API is on http://localhost:8080
just k8s-status   # scaled objects, deployments, pods
just k8s-down     # delete the cluster
```

`k8s-up` builds the four image targets, loads them into the cluster, installs a pinned KEDA release and applies
`deploy/kind`: local `:local` image tags, one API replica, the API as NodePort 30080 (mapped to host port 8080), the repo's
`./data` exposed to the workers through a hostPath volume (`deploy/kind/cluster.yaml`), and development credentials. Every
`kubectl` call is pinned to the `kind-backseat-driver` context. Try it with `curl -X POST localhost:8080/jobs`, then
`just k8s-status` while the caption queue drains.

## Release checklist

Run through this before tagging a release; each step lists what "good" looks like.

1. `just lint typecheck test` — all green, coverage ≥ 95 %.
2. `just test-compose` — system + smoke tests pass against the containerised stack.
3. **Batch + UI**: `just test-ui` (Selenium), then `just run --max-scenes 2` and `just ui` — the page lists every scene with each model's description,
   scores, working filters, no browser-console errors and no horizontal scrolling at phone width.
4. **Distributed stack**: `just compose up --build`, then `curl localhost:8080/ready` → 200;
   `POST /jobs` → 202; `GET /jobs/{id}` reaches `completed`; `GET /jobs/{id}/descriptions` has one entry per scene.
   `just compose logs ingest-worker` shows the task being received (worker failures must be visible there).
5. **Containers**: `docker run --rm <image> id` reports uid 10001; the API also starts with `--read-only --tmpfs /tmp
   --cap-drop ALL`.
6. **Kubernetes**: `kubectl kustomize deploy/k8s | kubectl apply --dry-run=server -f -` accepts every object (CI also
   validates the rendered YAML against the Kubernetes schemas); on a real cluster, `kubectl rollout status` succeeds for
   `api`, both workers and `ui`.
