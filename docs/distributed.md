# Distributed mode

The batch CLI is the primary deliverable: one process, one flow — `SceneLoader` → `Captioner` → JSON. Distributed mode is an **optional layer around that same flow**, not a rewrite of it. The queue workers call the same `SceneLoader` and `Captioner` Protocols and the same `describe_keyframe()` step the CLI pipeline uses, so what a scene's description *is* lives in one place; the queue only decides *where* each step runs.

```
Client ──REST──▶ API ──(1) create job──▶ Postgres
                  │
                  └─(2) IngestTask──▶ RabbitMQ [vlmscene.ingest]
                                          ▼
                              ingest-worker (NuScenesSceneLoader)
                                 │ set expected_scenes, then one CaptionTask per scene
                                 ▼
                          RabbitMQ [vlmscene.caption]
                                 ▼
                     caption-worker × N (BlipCaptioner, model loaded once)
                                 ▼
                      Postgres (scene_descriptions)  ◀── GET /jobs/{id}
```

## Services

| Service | Command | Role |
|---|---|---|
| `api` | `granian … vlmscene.api.app:app` | `POST /jobs` (202), `GET /jobs/{id}`, `GET /jobs/{id}/descriptions`, plus the synchronous `/describe` |
| `ingest-worker` | `vlm-scene-description worker ingest` | Reads the dataset, fans out one caption task per scene |
| `caption-worker` | `vlm-scene-description worker caption` | Captions one keyframe and stores the result; scale horizontally |
| `db-init` | `vlm-scene-description db init` | One-shot: creates the tables |
| `rabbitmq`, `postgres` | | Broker and job store |

Run it with `just up` (and `docker compose up --scale caption-worker=4` to add workers). The dataset must be in `./data`, mounted read-only into both workers.

## Design choices

- **Messages carry references, not pixels.** A `CaptionTask` holds the keyframe's `image_path`; workers read the shared `data` volume. Swapping in an object store would change `image_path` semantics only.
- **Job state is derived, not stored.** `pending` until ingest records `expected_scenes`, `running` while `completed < expected`, `completed` after. There is no "mark done" step to race between workers.
- **At-least-once, idempotent.** A message is acked only after its result is written. `(job_id, scene_token)` is the primary key and inserts use `ON CONFLICT DO NOTHING`, so redelivery is harmless.
- **Poison messages are bounded.** Queues are quorum queues with a delivery limit of 3; after that a message is dead-lettered to `vlmscene.dead` for inspection. A failed ingest therefore leaves its job `pending` — there is no `failed` state yet.
- **Fail fast at startup, tolerant at construction.** Clients never connect in their constructors (so tests and `--help` need no infrastructure); `/ready` reports broker and database reachability, and compose gates the API on both being healthy. The caption worker loads its model before consuming.
- **Every job has a `transaction_id`** (the caller's `X-Request-ID`, or a generated one). It is stored on the job, returned by the API, carried in every queue message body (and mirrored in the `X-Request-ID` header), and bound to every worker log line with the `job_id`, so one identifier follows a request across all services.

## Scaling

Caption workers are stateless consumers of one queue, so throughput scales with replica count (keep `caption_prefetch` small so work spreads evenly). On Kubernetes, scale them with KEDA on queue depth and let GPU node pools scale from zero. That manifest work is not in this repo yet.

## Not done yet

- An in-memory `JobQueue`/`JobStore` so the CLI could run these same worker classes in one process.
- A `failed` job state and a dead-letter consumer.
- Object storage instead of a shared volume; Kubernetes/KEDA manifests.
