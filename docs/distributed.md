# Distributed mode

The batch CLI is the primary deliverable: one process, one flow — `SceneLoader` → `Captioner` → JSON. Distributed mode is an **optional layer around that same flow**, not a rewrite of it. The queue workers call the same `SceneLoader` and `Captioner` abstract classs and the same `describe_keyframe()` step the CLI pipeline uses, so what a scene's description *is* lives in one place; the queue only decides *where* each step runs.

```
Client ──REST──▶ API ──(1) create job──▶ Postgres
                  │
                  └─(2) IngestTask──▶ RabbitMQ [backseat_driver.ingest]
                                          ▼
                              ingest-worker (NuScenesSceneLoader)
                                 │ set expected_scenes, then one CaptionTask per scene
                                 ▼
                          RabbitMQ [backseat_driver.caption]
                                 ▼
                     caption-worker × N (BackendCaptioner, model loaded once)
                                 ▼
                      Postgres (scene_descriptions)  ◀── GET /jobs/{id}
```

## Monolith vs. distributed

`BACKSEAT_DRIVER_MODE` picks how the API runs `/jobs`; `jobs.factory.build_job_backend` wires the matching `JobQueue` and `JobStore`.

| Mode | Queue / store | Used by |
|---|---|---|
| `monolith` (default) | `InProcessJobQueue` / `InMemoryJobStore` — the same `IngestWorker` and `CaptionWorker` handlers run on one background thread inside the API process, sharing its captioner | `just dev`, `just serve`: nothing but the API (and the dataset in `./data`) is needed. Jobs are lost on restart |
| `distributed` | `CeleryJobQueue` (RabbitMQ) / `PostgresJobStore` | `docker compose` and Kubernetes, which set the mode and run every service below; and `just dev-distributed` to debug the host-run API against local infrastructure |

To debug the distributed path locally, run `just dev-distributed` (starts RabbitMQ + Postgres in Docker and the API on the host with `BACKSEAT_DRIVER_MODE=distributed`), then `just worker-ingest` and `just worker-caption` in other terminals.

The API's HTTP surface is identical in both modes; only where the work runs differs.

## Services

| Service | Command | Role |
|---|---|---|
| `api` | `fastapi run backseat_driver/api/app.py` | `POST /jobs` (202), `GET /jobs/{id}`, `GET /jobs/{id}/descriptions`, plus the synchronous `/describe` |
| `ingest-worker` | `backseat-driver worker ingest` | Reads the dataset, fans out one caption task per scene |
| `caption-worker` | `backseat-driver worker caption` | Captions one keyframe and stores the result; scale horizontally |
| `db-init` | `backseat-driver db init` | One-shot: creates the tables |
| `rabbitmq`, `postgres` | | Broker and job store |

Each service has its own `docker/Dockerfile` target and dependency group: `api`, `ingest-worker` (nuscenes-devkit, no torch), `caption-worker` (torch, no nuscenes-devkit), and `cli` (everything, also used by `db-init`). Build one with `docker build -f docker/Dockerfile --target caption-worker .`.

Run it with `just up` (and `just compose up --scale caption-worker=4` to add workers), or on Kubernetes with `just k8s-apply` (see [Deployment](deployment.md)). The dataset must be in `./data`, mounted read-only into both workers.

## Design choices

- **Messages carry references, not pixels.** A `CaptionTask` holds the keyframe's `image_path`; workers read the shared `data` volume. Swapping in an object store would change `image_path` semantics only.
- **Job state is derived, not stored.** `pending` until ingest records `expected_scenes`, `running` while `completed < expected`, `completed` after. There is no "mark done" step to race between workers.
- **At-least-once, idempotent.** A message is acked only after its result is written. `(job_id, scene_token)` is the primary key and inserts use `ON CONFLICT DO NOTHING`, so redelivery is harmless.
- **Workers are Celery workers** (`backseat_driver/tasks.py`), over RabbitMQ quorum queues, with late acks and one message at a time. A task that fails is retried with backoff up to 3 times, except malformed messages, which are never retried. After that the failure is logged with its `transaction_id` and the message is dropped, so its job stays `pending`/`running` — there is no `failed` state or dead-letter queue yet. Remote control and gossip are off because RabbitMQ 4 rejects the transient queues they need.
- **Fail fast at startup, tolerant at construction.** Clients never connect in their constructors (so tests and `--help` need no infrastructure); `/ready` reports broker and database reachability, and compose gates the API on both being healthy. The caption worker loads its model before consuming.
- **Every job has a `transaction_id`** (the caller's `X-Request-ID`, or a generated one). It is stored on the job, returned by the API, carried in every queue message body (and mirrored in the `X-Request-ID` header), and bound to every worker log line with the `job_id`, so one identifier follows a request across all services.

## Scaling

Caption workers run the solo pool (the model loads once per process and CUDA is never forked), so scale by adding processes or containers. They are stateless consumers of one queue, so throughput scales with replica count. On Kubernetes they can autoscale on queue depth with KEDA (see [Deployment](deployment.md#autoscaling-and-the-local-kind-cluster)).

## Not done yet

- A `failed` job state, and a dead-letter queue for tasks that exhaust their retries.
- Object storage instead of a shared volume; GPU node pools.
- Autoscaling the API (needs metrics-server).
