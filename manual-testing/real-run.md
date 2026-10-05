# Real data and real model

CI builds a tiny synthetic nuScenes dataset. This run checks the loader against the real files and a person judges the
captions.

## Setup

```bash
uv sync --group dev
cp .env.example .env
```

The first `describe` downloads nuScenes v1.0-mini into `data/sets/nuscenes` (see
[Getting Started](../docs/getting-started.md)). Delete the folder to start clean.

## 1. Batch pipeline, local

```bash
just describe --camera front --model Salesforce/blip-image-captioning-base
```

Good looks like:

- It finishes without a traceback and writes `output/huggingface__Salesforce-blip-image-captioning-base.json`.
- The file has an entry for every scene in v1.0-mini (10), each with a non-empty description.
- Run it a second time: nothing is re-downloaded and the result is the same shape.

Also run with `--all-cameras --max-scenes 2` and confirm six cameras per scene come out.

## 2. Captions are sensible

Open five or more of the source images next to their descriptions. Good looks like:

- The caption matches what is in the picture (road, vehicles, weather, time of day), not another scene's.
- No scene gets an empty, repeated or garbled caption.
- Night and rain scenes are not described as clear daylight.

Repeat for each backend you ship:

| Backend | Command | Needs |
|---|---|---|
| HuggingFace | as above | the weights (about 1 GB) |
| Ollama | `just describe --backend ollama --model llava --camera front` | a running Ollama with the model pulled |
| Anthropic | `just describe --backend anthropic --model claude-haiku-4-5-20251001 --camera front --max-scenes 2` | `BACKSEAT_DRIVER_ANTHROPIC_API_KEY`; this is billed |

## 3. The API against the real model

```bash
just dev
curl http://127.0.0.1:8080/ready
curl -F "image=@data/sets/nuscenes/samples/CAM_FRONT/<any image>.jpg" http://127.0.0.1:8080/describe
```

Good looks like: `/ready` is 200 and `/describe` returns a caption for the image you sent.
