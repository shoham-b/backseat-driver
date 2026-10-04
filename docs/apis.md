# APIs

The HTTP API (`backseat_driver.api`, FastAPI) is the front door of the job flow and also captions single images on demand. `just dev` serves it on `:8080`; the interactive OpenAPI docs are at `/docs`. See [From pipeline to cluster](ladder.md) for what runs behind `/jobs`.

Successes return the documented model directly. Errors use `{"error": {"code": <int>, "status": "<phrase>", "message": "<detail>"}}`.

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Liveness probe: `200` if the process is running, no dependency checks |
| `GET` | `/ready` | Readiness probe: `200` only when the captioner is available, `503` otherwise |
| `POST` | `/describe` | Multipart image upload → `{"description": str, "model_name": str}` |
| `POST` | `/jobs` | Start a job over every scene in the dataset. Optional body `{"max_scenes": N}`. Returns the `Job` with `202` |
| `GET` | `/jobs` | Jobs, newest first. Query: `state`, `limit` (1 to 500, default 100) |
| `GET` | `/jobs/{job_id}` | Progress of a job: `pending`, then `running`, then `completed` |
| `GET` | `/jobs/{job_id}/descriptions` | Descriptions produced so far (all of them once the job is `completed`) |
| `GET` | `/images/{key}` | A keyframe image by dataset-relative key. Only `samples/` image keys; `ETag`, `304` on a matching `If-None-Match`, immutable caching |

Request handlers live in [`api/routers/`](https://github.com/shoham-b/backseat-driver/tree/main/backseat_driver/api/routers). The Python reference is in [API Reference](api.md).
