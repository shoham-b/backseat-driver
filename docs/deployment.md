# Deployment

CI exercises everything below except the production overlay (see [What CI checks](#what-ci-checks)); the parts that
can be checked without a cluster or a daemon are also pinned by `tests/integrationtests/test_deployment.py`.

## Images

`docker/Dockerfile` has one runtime target per service, all running as the unprivileged user `app` (uid 10001):

| Target | Entrypoint | Used for |
|---|---|---|
| `cli` | `backseat-driver` | the batch pipeline, the report UI, `db init` |
| `api` | `fastapi run …` on port 8080 | `/describe`, `/jobs`, `/health`, `/ready` |
| `ingest-worker` | `backseat-driver worker ingest` | reads the dataset's metadata tables from the bucket and fans out caption tasks (no torch, no dataset on disk) |
| `caption-worker` | `backseat-driver worker caption` | downloads one keyframe from the bucket and runs the VLM on it (torch, no dataset on disk) |

Model weights are cached under `HF_HOME` (`/home/app/.cache/huggingface`); mount a volume there to survive restarts.
`.github/workflows/docker.yml` publishes them as `ghcr.io/shoham-b/backseat-driver-{cli,api,ingest-worker,caption-worker}:latest` on every push to main (unstable). Each release (`release-please.yml`) publishes the same four images tagged with the release version, e.g. `:v0.2.0`; pin those in production.

## Docker Compose

| Goal | Command |
|---|---|
| Batch run → `./output/*.json` | `just compose --profile cli run --rm cli describe` |
| Model-comparison UI on <http://localhost:8081> | `just compose --profile ui up ui` |
| API + RabbitMQ + Postgres + workers | `just compose up --build` (API on <http://localhost:8080>) |
| Containerised system + smoke tests | `just test-system` |

Of the distributed services only the one-shot `dataset-upload` reads `./data`: it copies the dataset into the `s3` service (a development S3 store started with the stack) and the workers read it from there. The `cli` and `ui` services also mount `./data`, read-only, for the batch run. Results are written to `./output`. Because the image is non-root, a bind-mounted
`./output` that Docker created as root is not writable; either `mkdir output` and run with
`LOCAL_UID=$(id -u) LOCAL_GID=$(id -g)`, or leave both unset to run as root as before.

The `ui` service exits at startup when `./output` has no result files yet — run the pipeline first.

## Kubernetes

`deploy/k8s` is a Kustomize base (`kubectl apply -k deploy/k8s`) that creates the `backseat-driver` namespace and:

| Object | Notes |
|---|---|
| `api` Deployment (2) + Service | liveness `/health`, readiness `/ready` (VLM, broker and database reachable); serves `GET /images/{key}` from the dataset bucket, so it takes the same `DATASET_BUCKET` and `AWS_*` configuration as the workers and refuses to start without it |
| `ingest-worker` (1), `caption-worker` (2) | each from its own image; `kubectl -n backseat-driver scale deploy/caption-worker --replicas=N`, or autoscale (below). With KEDA the ingest Deployment is replaced by a Job per queued ingest task |
| `dataset-upload` Job | copies the dataset from the `nuscenes-data` volume into the bucket (skipping images already there); retries until the volume and the bucket are up |
| `db-init` Job | creates the tables; the API and workers recover on their own once it has succeeded |
| `postgres` StatefulSet, `rabbitmq` Deployment | evaluation-grade; point `BACKSEAT_DRIVER_DATABASE_URL` / `_RABBITMQ_URL` at managed services in production |
| `s3` Deployment + Service | development-only S3 store (in memory, any credentials) with the `nuscenes` bucket; in production delete `object-store.yaml` and set `BACKSEAT_DRIVER_DATASET_BUCKET`, the `AWS_*` credentials and (for non-AWS stores) `BACKSEAT_DRIVER_S3_ENDPOINT_URL` |
| `ui` Deployment + Service | the model-comparison report, built on every load from the completed jobs on the API (`BACKSEAT_DRIVER_UI_ALL_JOBS`) with images proxied from it; mounts no volume and needs only the API's address. `BACKSEAT_DRIVER_UI_PUBLIC_API_URL` is where the browser reaches the API for the live card (a `port-forward` by default) |
| `nuscenes-data` PVC | the dataset (read-only; mounted only by the `dataset-upload` Job: not by a worker, the UI or the example run job) |

```bash
kubectl apply -k deploy/k8s
# nuScenes can't be redistributed: copy data/sets/nuscenes into the nuscenes-data volume, e.g. with a throwaway pod.
kubectl apply -f deploy/k8s/examples/run-job.yaml     # submit a job to the API, wait for the workers
kubectl -n backseat-driver port-forward svc/api 8080:80
kubectl -n backseat-driver port-forward svc/ui 8081:80
```

The config sets `BACKSEAT_DRIVER_MODE=distributed`. Without it the API would use its default monolith mode and run `/jobs`
inside the API pods, never touching the workers.

Before using it for real, replace the development credentials in `config.yaml` (the `Secret` and the RabbitMQ URL) and
pin the image tags with the `images:` block in `kustomization.yaml`. Both PVCs are `ReadWriteOnce`: on a multi-node
cluster, pin the pods that share a volume to one node. No worker mounts a volume, so the workers can run on any node:
they only reach the broker, Postgres and the dataset bucket.

## Production

`deploy/production` is a Kustomize overlay on the base (`kubectl apply -k deploy/production`). It deploys only the
stateless parts (API, UI, workers, Jobs) and expects the stateful ones to be external:

| Needs | Why it is not in the overlay |
|---|---|
| Managed Postgres | the base StatefulSet has one 5Gi volume and no backups |
| RabbitMQ with the management plugin | the base Deployment has no volume, so a restart loses queued work; KEDA also reads queue depth from the management API |
| A real S3 bucket | the base store is in memory |

What the overlay changes: the dev Postgres, RabbitMQ, S3 mock and Secret are deleted; image tags are pinned to a release
(the release PR bumps them); the ConfigMap loses the broker URL and the S3 endpoint; KEDA autoscaling is on; and it adds
an Ingress with TLS, NetworkPolicies (default-deny ingress; the API accepts only the ingress controller and the UI, the UI
only the ingress controller), PodDisruptionBudgets, zone and node spreading, a 120 s grace period for caption workers so an
in-flight caption finishes on SIGTERM, memory limits on the ingest Jobs and the UI, and two UI replicas.

Before applying, replace the `example.com` hosts and the `REPLACE-ME` bucket and region in `kustomization.yaml` and
`ingress.yaml` (the API host appears in the Ingress and `UI_PUBLIC_API_URL`, the UI host in the Ingress and
`CORS_ORIGINS`), then create two Secrets in the `backseat-driver` namespace:

- `backseat-driver-secrets`: `BACKSEAT_DRIVER_DATABASE_URL`, `BACKSEAT_DRIVER_RABBITMQ_URL`, `AWS_ACCESS_KEY_ID`,
  `AWS_SECRET_ACCESS_KEY` (or use workload identity instead) and, for the anthropic backend,
  `BACKSEAT_DRIVER_ANTHROPIC_API_KEY`. Create it with external-secrets, sealed secrets or similar, never from a file in git.
- `rabbitmq-management`: `host`, the broker's management API URL with credentials, read by KEDA.

Not covered, by choice:

- **Model weights** are still downloaded from the model hub into an `emptyDir` on every pod start, so each scale-up pays a
  cold start and depends on the hub. Baking the weights into the worker image is the fix and needs an image change.
- **Egress** is unrestricted; the destinations differ per cluster.
- **Caption workers have no liveness probe.** The solo pool cannot answer while it captions, so a probe would kill busy workers.
- **`readOnlyRootFilesystem`** is set on the API only (with `/tmp` and the model cache as writable volumes); the
  workers and UI have not been tried that way.

## Autoscaling and the local kind cluster

`deploy/components/keda-autoscaling` is an optional kustomize component that scales the workers on RabbitMQ queue depth
with [KEDA](https://keda.sh). Queue length measures pending work directly, whereas a solo-pool worker's CPU says little
about how far behind it is. It needs KEDA in the cluster and a `rabbitmq-management` Secret (key `host`: the management API
URL with credentials) from the overlay that uses it. KEDA resolves that host from its own namespace, so it must
include the namespace, e.g. `http://guest:guest@rabbitmq.backseat-driver:15672/`: a bare `rabbitmq` does not resolve.

| Deployment | Queue | Scale | Replicas |
|---|---|---|---|
| `caption-worker` | `backseat_driver.caption` | 1 per 20 waiting scenes | 1–8 |
| `ingest-worker` (a `ScaledJob`) | `backseat_driver.ingest` | one Job per waiting ingest task, none while the queue is empty | 0–3 at a time |

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
`./data` exposed to the `dataset-upload` Job through a hostPath volume (`deploy/kind/cluster.yaml`), and development credentials. Every
`kubectl` call is pinned to the `kind-backseat-driver` context. Try it with `curl -X POST localhost:8080/jobs`, then
`just k8s-status` while the caption queue drains.

### Continuous testing on kind

The `kind` job in `.github/workflows/ci.yml` runs the kind deployment in CI: it builds the api, ingest-worker and
caption-worker images from `docker/Dockerfile`, creates the cluster, installs the pinned KEDA release (the Justfile's
`keda_version`), applies `deploy/kind-ci`, runs the system and smoke tests against the API, and then
`deploy/kind-ci/check-scaling.sh`. That script queues captions, expects KEDA to scale `caption-worker` up (at least 3
replicas), every caption to be recorded, and the workers to scale back to 1.

`deploy/kind-ci` is `deploy/kind` plus a stub model server (no weights to download), small resource requests so many
replicas fit on a runner, and fast autoscaling (5 s polling, 1 scene per replica per 5 queued, 30 s scale-down window). It leaves out the `cli`
image and the `ui` Deployment to save build and load time: `db-init` runs on the API image, which has the same CLI, and
`ui` only shows anything once a job has completed.
The manifests, probes and ScaledObjects under test are otherwise the real ones. Like `test-system` and
`deploy-config`, the job runs on every push to the main branch and on pull requests that touch `docker/` or `deploy/`
(the `deployment` filter of the `changes` job).

The autoscaling component also switches RabbitMQ to the `rabbitmq:4-management` image and exposes port 15672, because
KEDA reads queue depth from the management API.

## What CI checks

Every step a release used to be checked by hand for runs in CI: lint, types and the unit and integration tests (on Linux
and Windows), the report UI in headless Chrome, the built wheel installed into an empty environment, the Compose stack
end to end (`just test-system`), the Kubernetes base on a kind cluster with autoscaling, the schemas of every manifest, a strict build of these docs,
and that the pods start as non-root with every capability dropped (the API with a read-only root filesystem). What CI cannot do (the real dataset, the quality of
the captions, how the report looks) is in the repository's
`manual-testing/` folder, which is not part of these docs.
