# Design Decisions

This page records the design questions that came up while shaping this pipeline, the options considered for each, and the decision actually taken. It complements [Architecture](architecture.md), which describes the system as built — this page explains *why* it was built that way, and which alternatives were deliberately not chosen.

The read → process → write shape is fixed by the assignment. Nearly all the real design space lives inside "process" (how a scene becomes a caption) and at the seams between the three stages. Each decision below is recorded as: the question, the options, and the choice — with the condition that would flip it.

## Implementation status

The object model, method signatures, and calls between objects are implemented and type-check (`just typecheck`); the leaf logic behind each external dependency (`nuscenes-devkit` traversal in `NuScenesSceneLoader._keyframe_for_scene`/`_middle_sample`, the HF pipeline load/inference in `BlipCaptioner.load`/`caption`, the file write in `write_json`) raises `NotImplementedError` pending a follow-up pass. `tests/unittests/test_pipeline.py` passes today (it only exercises the wiring, via fakes); `test_captioner.py`, `test_nuscenes_loader.py`, and `test_writer.py` fail on the stubs by design — they're the acceptance spec for that follow-up pass, not a regression.

Two signature changes landed in this pass, both consequences of the review in "Missing corners" below:

- **`Captioner` gained `model_name` (property) and `load()`.** `ScenePipeline` and `api/routers/describe.py` previously each had their own way of getting at the model name (a constructor arg on the former, a `getattr(..., "unknown")` fallback on the latter) — both now just read `captioner.model_name`. `load()` exists so a caller can eager-load the model instead of paying that cost inside the first `caption()` call, but **nothing calls it yet** — wiring it into `api/app.py`'s `lifespan()` was deferred because that function runs unconditionally at app startup, including under `TestClient`, and `BlipCaptioner.load()` is currently a stub that raises. Wiring it in before the leaf logic is filled in would break every integration/smoke/system test that boots the app, not just the two unit-test files that are supposed to fail right now. Do this in the same pass that fills in `BlipCaptioner.load()`.
- **`api/routers/describe.py` now calls `captioner.caption()` via `run_in_threadpool`.** `caption()` is synchronous and CPU-bound; calling it directly inside an `async def` route blocks the whole event loop for the request's duration. This was safe to fix now because it only changes how the API layer calls the (already-Protocol'd) captioner, not what the captioner does.

## Settled by convergence

These three came up independently from two different sources (this design conversation, and a second review) and agreed without prompting — treated as high-confidence, not just preference.

| Decision | Choice | Why |
|---|---|---|
| VLM backend seam | `Captioner` as a `Protocol`, `BlipCaptioner` as the concrete implementation (Strategy) | The one thing stated up front as likely to change (local BLIP → hosted API VLM later) and the one thing slow enough to be worth faking in tests |
| Dataset access seam | `NuScenesSceneLoader` wraps `nuscenes-devkit` behind `SceneLoader` (Adapter) | Isolates the rest of the codebase from the devkit's dict/token-graph API; a devkit version bump only touches this one file |
| Wiring | Constructor injection — `ScenePipeline(loader, captioner, model_name)`, concrete instances built at the CLI entry point, not inside the pipeline | Makes `ScenePipeline` importable and unit-testable without ever importing `nuscenes-devkit` or `transformers` |

## Open questions, decided

### 1. Should the loader return a list or yield a generator?

**Options:** `load_keyframes() -> list[SceneKeyframe]` (current) vs. `Iterator[SceneKeyframe]`.

**Decision: keep the list.** The object being held in memory is `SceneKeyframe` — four short strings, not image bytes; the actual image is opened lazily, one at a time, inside `BlipCaptioner.caption()`. For v1.0-mini (10 scenes) or even the full ~850-scene dataset, the list is kilobytes. A generator is the right instinct for a dataset large enough that even enumerating *metadata* is expensive (e.g., paging through a remote catalog) — that's not this dataset.

**Revisit if:** the loader starts reading image bytes eagerly, or the scene catalog itself becomes large enough that building the full list up front is measurably slow.

### 2. Should the writer be a plain function or a `Sink` interface?

**Options:** `write_json(descriptions, path)` (current) vs. a `Sink` Protocol with `JsonSink`/other implementations, injected into the pipeline like the loader and captioner.

**Decision: keep it a function.** Promoting a seam to an interface is worth it when something either varies or needs to be faked in a test to avoid a slow/external dependency. Neither is true here: there's one output format, and testing pure JSON serialization needs no fake — it's called directly against a temp path. Making it a third injected Protocol would add a matching interface for a case with no actual variation yet, which is the thing we've been deliberately avoiding throughout this design.

**Revisit if:** a second output format (CSV, a DB row, a message queue) is actually needed — promoting a function to a Protocol at that point is a small, low-risk refactor.

### 3. Output format: single JSON array or JSON Lines?

**Options:** one JSON array, all results (current `write_json`) vs. JSONL (one JSON object per line, append-friendly, streamable).

**Decision: single JSON array.** The assignment asks for "a simple structured form ... one entry per scene" — a JSON array is the most direct, most human-readable reading of that, and it's what every downstream tool (`jq`, `json.load`, a browser) expects by default with no special handling. JSONL earns its keep when a consumer processes results incrementally as they're produced (streaming ingestion, append-only logs) — nothing in this pipeline does that; the whole batch is written once, at the end, after every scene is described.

**Revisit if:** a downstream consumer needs to start processing results before the full batch finishes, or the scene count grows large enough that holding the whole result list in memory before writing becomes a real constraint.

### 4. Per-scene failure handling: fail-fast or catch-and-continue?

**Options:** let a captioning failure on one scene raise and abort the whole run (current — `ScenePipeline.run()` has no `try`/`except` around `self._captioner.caption(...)`) vs. catch per-scene, record the failure in the output, and continue with the rest.

**Decision: fail-fast, keep it as built.** This matches the project's own stated convention (`AGENTS.md`: "never swallow exceptions... bugs caught immediately are far easier to debug than silent failures discovered later") and, for a 10-scene batch, a loud crash on scene 3 is more useful than a JSON file that silently ships with 9 entries and a shape nothing validates against.

**Revisit if:** the scene count grows large enough that one bad image souring an otherwise-successful run of hundreds becomes the actual operational problem — at that scale, catch-and-record-per-scene (with the failure visible in the output, not swallowed) becomes the better default.

### 5. Process step: local model vs. hosted VLM

**Options:** local BLIP via `transformers` (current) vs. a hosted VLM (Claude/GPT-4V-class) behind the same `Captioner` Protocol.

**Decision: local BLIP.** The assignment explicitly says "no need for large models or GPU inference... a small/basic VLM is fine," and a container that needs a live API key and network egress at runtime is a materially different deployment story than one that's fully self-contained. The `Captioner` Protocol already makes a hosted backend a same-shaped addition later — a new class, no changes to `ScenePipeline`.

**Revisit if:** description quality becomes the actual bottleneck rather than pipeline structure — that's a model-swap, not an architecture change, by design.

### 6. Prompted vs. unprompted captioning

**Options:** BLIP's unconditional `image-to-text` pipeline (current — produces a generic caption) vs. a prompt-capable VLM steered toward driving-specific detail ("note hazards, traffic, pedestrians").

**Decision: unprompted, generic captioning.** The assignment's ask is "a short natural-language description of the scene" — not hazard analysis. Steering toward domain-specific detail is a real, reasonable next step for the repo's own "backseat driver" framing, but it's a scope decision beyond what was actually asked, not an architecture one.

**Revisit if:** the description's actual consumer needs driving-specific structure (hazards, traffic state) rather than a general caption — at that point it's a prompt/model change behind the same `Captioner` interface, not a pipeline redesign.
