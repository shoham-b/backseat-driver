# Design Decisions

This page records the design questions that came up while shaping this pipeline, the options considered for each, and the decision actually taken. It complements [Architecture](architecture.md), which describes the system as built — this page explains *why* it was built that way, and which alternatives were deliberately not chosen.

The read → process → write shape is fixed by the assignment. Nearly all the real design space lives inside "process" (how a scene becomes a caption) and at the seams between the three stages. Each decision below is recorded as: the question, the options, and the choice — with the condition that would flip it.

## Settled by convergence

These three came up independently from two different sources (this design conversation, and a second review) and agreed without prompting — treated as high-confidence, not just preference.

| Decision | Choice | Why |
|---|---|---|
| VLM backend seam | `Captioner` as an abstract class, `HuggingFaceCaptioner` as the concrete implementation (Strategy) | The one thing stated up front as likely to change (local BLIP → hosted API VLM later) and the one thing slow enough to be worth faking in tests |
| Dataset access seam | `NuScenesSceneLoader` wraps `nuscenes-devkit` behind `SceneLoader` (Adapter) | Isolates the rest of the codebase from the devkit's dict/token-graph API; a devkit version bump only touches this one file |
| Wiring | Constructor injection — `ScenePipeline(loader, captioner, model_name)`, concrete instances built at the CLI entry point, not inside the pipeline | Makes `ScenePipeline` importable and unit-testable without ever importing `nuscenes-devkit` or `transformers` |

## Open questions, decided

### 1. Should the loader return a list or yield a generator?

**Options:** `load_keyframes() -> list[SceneKeyframe]` (current) vs. `Iterator[SceneKeyframe]`.

**Decision: keep the list.** The object being held in memory is `SceneKeyframe` — four short strings, not image bytes; the actual image is opened lazily, one at a time, inside `HuggingFaceCaptioner.caption()`. For v1.0-mini (10 scenes) or even the full ~850-scene dataset, the list is kilobytes. A generator is the right instinct for a dataset large enough that even enumerating *metadata* is expensive (e.g., paging through a remote catalog) — that's not this dataset.

**Revisit if:** the loader starts reading image bytes eagerly, or the scene catalog itself becomes large enough that building the full list up front is measurably slow.

### 2. Should the writer be a plain function or a `Sink` interface?

**Options:** `write_json(descriptions, path)` (current) vs. a `Sink` abstract class with `JsonSink`/other implementations, injected into the pipeline like the loader and captioner.

**Decision: keep it a function.** Promoting a seam to an interface is worth it when something either varies or needs to be faked in a test to avoid a slow/external dependency. Neither is true here: there's one output format, and testing pure JSON serialization needs no fake — it's called directly against a temp path. Making it a third injected abstract class would add a matching interface for a case with no actual variation yet, which is the thing we've been deliberately avoiding throughout this design.

**Revisit if:** a second output format (CSV, a DB row, a message queue) is actually needed — promoting a function to an abstract class at that point is a small, low-risk refactor.

### 3. Output format: single JSON array or JSON Lines?

**Options:** one JSON array, all results (current `write_json`) vs. JSONL (one JSON object per line, append-friendly, streamable).

**Decision: single JSON array.** The assignment asks for "a simple structured form ... one entry per scene" — a JSON array is the most direct, most human-readable reading of that, and it's what every downstream tool (`jq`, `json.load`, a browser) expects by default with no special handling. JSONL earns its keep when a consumer processes results incrementally as they're produced (streaming ingestion, append-only logs) — nothing in this pipeline does that; the whole batch is written once, at the end, after every scene is described.

**Revisit if:** a downstream consumer needs to start processing results before the full batch finishes, or the scene count grows large enough that holding the whole result list in memory before writing becomes a real constraint.

### 4. Per-scene failure handling: fail-fast or catch-and-continue?

**Options:** let a captioning failure on one scene raise and abort the whole run (current — `ScenePipeline.run()` has no `try`/`except` around `self._captioner.caption(...)`) vs. catch per-scene, record the failure in the output, and continue with the rest.

**Decision: fail-fast, keep it as built.** This matches the project's own stated convention (`AGENTS.md`: "never swallow exceptions... bugs caught immediately are far easier to debug than silent failures discovered later") and, for a 10-scene batch, a loud crash on scene 3 is more useful than a JSON file that silently ships with 9 entries and a shape nothing validates against.

**Revisit if:** the scene count grows large enough that one bad image souring an otherwise-successful run of hundreds becomes the actual operational problem — at that scale, catch-and-record-per-scene (with the failure visible in the output, not swallowed) becomes the better default.

### 5. Process step: local model vs. hosted VLM

**Options:** local BLIP via `transformers` vs. a local Ollama model vs. a hosted VLM (Claude) behind the same `Captioner` abstract class.

**Decision: all three, with local BLIP as the self-contained example.** The assignment explicitly says "no need for large models or GPU inference... a small/basic VLM is fine," and a container that needs a live API key and network egress at runtime is a materially different deployment story than one that's fully self-contained, so the HuggingFace backend needs neither. Because the runtime (`CaptionBackend`) and the model (`CaptionModel`) are separate from `ScenePipeline`, the Ollama and Claude backends were each a new class with no pipeline changes. They give richer, prompt-driven descriptions and let the report compare models side by side; the hosted one is billed per request and needs an API key.

**Revisit if:** a backend's dependencies or maintenance cost outweigh what it adds to the comparison — dropping one is a delete, not an architecture change.

### 6. Prompted vs. unprompted captioning

**Options:** BLIP's unconditional `image-to-text` pipeline (produces a generic caption) vs. a prompt-capable VLM steered toward driving-specific detail ("note hazards, traffic, pedestrians").

**Decision: both, behind one `CaptionModel`.** The HuggingFace backend captions unconditionally, which matches the assignment's ask of "a short natural-language description of the scene". The Ollama and Claude backends are prompt-driven and share one driving-scene prompt (`SCENE_PROMPT`) that asks for a short comma-separated keyword list, the shape of the nuScenes labels the report scores against by word overlap, so their output is comparable with each other and is not judged on phrasing. BLIP cannot take a prompt, so it stays a plain caption and is not comparable with the others on format. The prompt is part of the model, so it changes without touching the pipeline.

**Revisit if:** the description's actual consumer needs driving-specific structure (hazards, traffic state) rather than a general caption — at that point it's a prompt/model change behind the same `Captioner` interface, not a pipeline redesign.

## Distributed mode and the monolith

The questions from here on came up while making the job processing work as separate services and as one process. They are kept in the order they were decided, because each answer changed the next question. [Distributed mode](distributed.md) describes the result.

### 7. Where does the monolith keep its jobs?

**Options:** in memory only; a SQLite file; or require Postgres even for local development.

**Decision: a SQLite file.** The monolith exists so `just dev` needs nothing but the API and the dataset on disk. In-memory state made a job id useless after a restart, and made it impossible to list past runs. SQLite is a file, not a service, so it keeps that promise while fixing both: `SqlJobStore` is the class that serves Postgres, run over a SQLite file (`BACKSEAT_DRIVER_JOBS_DB_PATH`, default `output/jobs.db`; empty keeps jobs in memory), so job ids, progress and descriptions survive a restart and `GET /jobs` lists earlier runs. The store was renamed from `PostgresJobStore` because it no longer is only that. Requiring Postgres was rejected because it would end the no-infrastructure local workflow.

Small details: `created_at` has a client-side microsecond default, because `CURRENT_TIMESTAMP` has one-second resolution on SQLite and several jobs created within a second must still list newest first; the engine sets a lock timeout and `check_same_thread=False`, because the API threads and the in-process worker thread share the connection pool.

What is **not** persisted is the in-process queue. A job that was running when the process stopped keeps its recorded progress, but its remaining scenes are never captioned and it stays `running`. That is the same gap as the missing `failed` state.

**Revisit if:** a monolith job must resume after a restart; the queue would then need to be persisted too.

### 8. Why two workers (ingest and caption) and not one?

**Options:** one worker that reads the dataset and captions every scene; or two queue consumers, `ingest` and `caption`.

**Decision: two.** They differ in everything that matters for scaling. Ingest opens the dataset, counts the scenes and publishes one message per scene: I/O-bound, once per job, cheap. Captioning runs the model once per scene: CPU/GPU-bound, many tasks per job, and the only step worth scaling. Separate workers mean caption replicas scale from the queue depth while ingest stays small, and each gets its own image (`ingest-worker` has nuscenes-devkit and no torch; `caption-worker` has torch and no devkit), so GPU nodes carry only the model. Ingest is not scaled because it only pushes to the queue.

**Revisit if:** captioning never needs more than one process. Then one worker would be simpler, and the monolith mode already is exactly that.


### 9. How is the data passed between the services?

**Options:** put the image bytes in the queue message; put a reference in the message and read the file from somewhere shared; or send a reference to an object store.

**Decision: messages carry small JSON with references, results go to Postgres.** The API publishes an `IngestTask` (job id, transaction id, `max_scenes`), ingest publishes one `CaptionTask` per scene (the `SceneKeyframe` plus where the image is), and the caption worker writes its `SceneDescription` to Postgres rather than back through the queue. Celery keeps no results. Images do not travel in messages: that would bloat RabbitMQ with payloads and re-send the same bytes on every redelivery.


### 10. How does a caption worker on another machine get the image?

The first design was a shared volume: both workers mounted the same `./data` (or one Kubernetes claim) at the same path, and the message carried the path. That only works on one machine. Four ways out were weighed:

| Option | Verdict |
|---|---|
| Shared network volume (NFS and similar) | Rejected. It needs no code change, but it is a shared filesystem to run, it can become the bottleneck, and `ReadWriteOnce` claims already forced "pin the pods to one node". |
| Object storage (S3, GCS, MinIO) | **Chosen.** Workers on any machine reach it with credentials and an endpoint, with nothing mounted. |
| Image bytes inside the task | Rejected for the reason in question 9. |
| Every worker downloads the whole dataset to local disk | Rejected. Every replica would pull the full dataset (a few GB for mini, far more for the full set) for the sake of one image per task. |

The `ImageStore` port (`read/`) keeps this swappable: `uri_for(key)` and `local_copy(uri)`, with `LocalImageStore` for the monolith (the key already is a path, nothing is copied or deleted) and an S3-compatible adapter over boto3 for the distributed mode. Credentials come from boto3's standard `AWS_*` chain, not from `Settings`; the bucket has no default and the workers refuse to start without one.


### 11. What goes into the bucket, and when?

**First attempt:** the ingest worker uploaded each keyframe image into the bucket as part of every job (under `keyframes/<scene token>/...`), so the object store only ever held what was about to be captioned. It worked, but it was the wrong place for the copy: every job re-uploaded the same images, ingest still needed the dataset mounted, and so one volume stayed in the picture.

**Decision: upload the dataset once, and make the bucket its home.** A one-time `backseat-driver dataset upload` copies the metadata tables (`<version>/*.json`) and the images of the configured camera into the bucket, keeping the nuScenes layout, and skips anything already there so it can be rerun. After that:

- **Ingest** downloads only the small metadata tables to a scratch directory and runs the devkit over them to find the keyframes. A keyframe's `image_path` becomes its dataset-relative key (`samples/CAM_FRONT/<name>.jpg`) and the task carries that key's URI.
- **Caption workers** fetch that one object, caption it and delete it.
- **No worker mounts the dataset.** Only the upload step reads it from disk.

Two details came out of testing it. The devkit refuses to open a dataset unless every map file named in `map.json` exists, so ingest creates empty placeholders for them instead of downloading the maps (`open_nuscenes_tables`). And sweeps and maps are not uploaded at all, because no worker reads them.

**Revisit if:** the full dataset's metadata tables become too large to download per job. They could then be cached on the ingest worker's disk, or the keyframes precomputed once and stored.


### 12. Which S3-compatible server for local development?

**Options:** MinIO, LocalStack, Adobe S3Mock, a cloud bucket.

**Decision: Adobe S3Mock, development only.** MinIO was the first choice, but its images could no longer be pulled (not from Docker Hub, and not from quay.io, which answered 401), so the compose file and manifests that were written for it could not run. S3Mock pulled and worked with boto3 for upload, download and listing, creates the bucket from an environment variable, and accepts any credentials. It is only a stand-in: it is in-memory, and production points `BACKSEAT_DRIVER_DATASET_BUCKET` and the `AWS_*` credentials at a real bucket and drops `deploy/k8s/object-store.yaml`.


### 13. Should the monolith use the object store too?

**Options:** keep the monolith local-only; or add a setting (say `BACKSEAT_DRIVER_DATASET_STORE=local|s3`) so the single-process mode can also read the dataset from the bucket, separating "how jobs run" from "where the dataset lives".

**Decision: local-only.** The monolith exists so `just dev` needs nothing but the API and the dataset on disk. It already skips the queue and the database for that reason, and the bucket belongs in the same category: infrastructure that exists to connect separate machines. A process that runs ingest and captioning together has no use for it. A switch would also add a second way to configure the dataset location, which can silently change what a stray bucket setting in `.env` does. The S3 path is exercised in distributed mode (`just dev-distributed` with `just dataset-upload`), which is also where it matters.

**Revisit if:** there is a need to run the API on a machine without the dataset but without a broker, which has not come up.


### 14. Where does ingest run: the API, a worker, or a Job?

**Options:** the API does the fan-out itself as a background task; an always-on ingest worker; or a run-to-completion Job per request.

The API option is attractive now that ingest only reads metadata, and the monolith already works that way. It was not chosen for the distributed mode: it puts nuscenes-devkit into an API image that is deliberately kept without it, runs the metadata load and fan-out on a serving pod, and has no recovery if the pod dies after answering 202 but before publishing every message (the job would stay `running` forever).

**Decision: keep the queue, and run ingest as a Job per queued task.**

- The API still publishes an `IngestTask`, so the message is durable and redelivered if the Job dies.
- On Kubernetes with KEDA, a `ScaledJob` starts one Job per waiting ingest message (`worker ingest --once`) that handles it and exits, so nothing runs while the queue is empty. The component deletes the always-on Deployment in its favour.
- Without KEDA (the base manifests) and in docker compose, ingest stays a plain long-running worker consuming the same queue, so everything works without KEDA installed.

**Why `--once` is not a Celery worker that stops.** The obvious implementation was to let a normal Celery worker run and make it shut down after its first task. Run against a real RabbitMQ, that handled all three queued messages: with prefetch the next message is started before the shutdown flag is looked at. `--once` therefore fetches a single message with a plain `basic_get`, runs it through the registered task (retries included), and acks it only afterwards. A task that still fails after its retries is dropped, as with the Celery workers, and the Job exits non-zero so the failure is visible. A Job that crashes before the ack leaves the message to be redelivered to the next Job. This was checked on a real RabbitMQ: three messages queued, one handled, two left.

**Revisit if:** the Job's pod start-up cost starts to dominate a job's latency; an always-on worker with a short idle timeout would then be the better trade.


### 15. Where does the report UI get its data and images?

**Options:** keep reading result files and a dataset volume; have the UI talk to the database and the bucket directly; or have it read everything from the API.

**Decision: from the API.** A finished job's descriptions already come from `GET /jobs/{id}/descriptions`, and the missing piece was the image bytes, so the API gained `GET /images/{key}`. The UI holding database or bucket credentials was rejected: it would put them in a second service for no benefit, and the API is the one place that already knows how to read both. `report --job <id>` (repeatable, one job per model) embeds the images it fetches, so the report needs the API and nothing else.

Details that came with it:

- **The API goes through a business-logic layer.** The route does not read the store: `ImageService` validates the key, reads the image, and turns a missing object into the domain's `NotFoundError`, so a store's own errors (a missing file, a missing S3 object) never reach the HTTP layer. That is the same layering the rest of the API follows.
- **The endpoint is not a file server.** It serves only keys under `samples/` with an image suffix, rejects empty, `.` and `..` segments and backslashes before the store is asked, and the local store refuses any key that resolves outside the dataroot. Metadata tables are not served.
- **HTTP caching.** Images never change under their key, so responses carry an `ETag` and `Cache-Control: public, max-age=86400, immutable`, and a matching `If-None-Match` gets `304`. That is the whole caching story for the API; nothing is cached on the server.
- **One error format.** The API and the report UI server answer errors in the same JSON envelope (`error_format.error_body`, the Google API error format), and `HttpStatusError` carries an upstream status so the UI can pass a missing image on as a 404 instead of calling every upstream failure a bad gateway.
- **The API needs the bucket in distributed mode.** A distributed `Settings` cannot be built without `BACKSEAT_DRIVER_DATASET_BUCKET`, so the API fails when its settings load, like the workers. Its image gained the S3 client.
- **A running job is an error.** The report is built when the command runs, and a partial one would look complete, so `--job` fails fast on a job that is not `completed`.

### 16. Making the report UI independent of volumes and of job ids

Reading from the API still left two limits: the deployed UI mounted the dataset volume (it served `describe` result files whose images are local paths), and job ids had to be given when it started. Neither was worth keeping.

**The UI discovers jobs itself.** `BACKSEAT_DRIVER_UI_ALL_JOBS` makes the UI re-read the completed jobs from `GET /jobs` on every page load, so a job that finishes shows up on the next refresh and no id has to be passed. Where several jobs ran the same model the newest one wins, so a rerun replaces rather than duplicates. The static `report` command is unchanged and still embeds everything.

**The UI proxies images, it does not embed them.** A page of hundreds of scenes with base64 images would be many megabytes per load. Instead the page points each image at the UI's own `/images/<key>`, which forwards to the API (the same key rule as the API's endpoint, checked before anything is forwarded) and returns the bytes with immutable caching headers, so the browser fetches each image once. The browser only ever talks to the UI: no CORS, no second address to expose. Result files given on the command line keep their embedded images, so local use is unchanged.

**The UI is a FastAPI app, not a hand-written server.** It began as a stdlib `BaseHTTPRequestHandler`, which meant hand-rolled routing, error mapping and headers beside an API that already has all of that. It is now a small FastAPI app run like the API (`fastapi run`, `just ui`), with no CLI command of its own and its options as `BACKSEAT_DRIVER_UI_*` settings: the `ApiReportSource` and the page are built per request through `Depends` chains from `Settings`, errors go through exception handlers into the API's JSON envelope (`error_body`), and tests drive it in-process with `httpx.ASGITransport` instead of real sockets. The cost is `fastapi[standard]` in the `cli` group, which the API image already has.

**The deployed UI mounts nothing.** `ui.yaml` drops both volumes and runs `fastapi run` with `BACKSEAT_DRIVER_UI_ALL_JOBS` and `BACKSEAT_DRIVER_API_URL=http://api`; its readiness probe is a new `/healthz` that does not call the API, because a probe that depends on the API would take the UI out of rotation whenever the API blinked. `BACKSEAT_DRIVER_UI_PUBLIC_API_URL` is where the *browser* reaches the API for the live-inference card (a port-forward by default), separate from `BACKSEAT_DRIVER_API_URL` that the UI process itself uses. The example `describe` Job mounts nothing either: it runs `describe --mode distributed` against the API, so the UI shows its job like any other.

**Revisit if:** the UI should filter or page through many jobs; the listing is capped at 500 and the newest-per-model rule is applied in the UI.

### What is still open

- **No `failed` job state, and no recovery of interrupted jobs.** A task that exhausts its retries is dropped and its job stays `running`; so does a monolith job whose process stopped before its in-process queue drained.
- **Nothing expires the uploaded dataset.** It is the source of truth, so it stays until deleted; give the bucket whatever lifecycle rule suits the dataset.
- **Old queued messages are rejected.** `CaptionTask.image_uri` is required, so tasks queued by an earlier version fail validation.
- **The full Docker stack and a real cluster were not run for this change.** Unit and integration tests, the rendered manifests, `docker compose config`, a boto3 round trip against S3Mock and the RabbitMQ `basic_get` check were.
