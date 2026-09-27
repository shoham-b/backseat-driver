# CLI Reference

All commands are run via `uv run vlm_scene_description <command>`.

Global help: `uv run vlm_scene_description --help`

---

## `--version` / `-V`

Print the installed version and exit.

```bash
uv run vlm_scene_description --version
# vlm_scene_description 0.1.0
```

---

## `run`

Describe every scene in a nuScenes dataset and write the results to JSON. This is the pipeline the
assignment asks for.

```bash
uv run vlm_scene_description run [OPTIONS]
```

| Option | Env var | Default | Description |
|---|---|---|---|
| `--dataroot` | `VLM_SCENE_DESCRIPTION_NUSCENES_DATAROOT` | `data/sets/nuscenes` | Path to the local dataset |
| `--version` | `VLM_SCENE_DESCRIPTION_NUSCENES_VERSION` | `v1.0-mini` | nuScenes dataset version |
| `--camera` | `VLM_SCENE_DESCRIPTION_CAMERA_CHANNEL` | `CAM_FRONT` | Camera channel used as the representative frame |
| `--model` | `VLM_SCENE_DESCRIPTION_VLM_MODEL_NAME` | `Salesforce/blip-image-captioning-base` | HuggingFace image-to-text model |
| `--output` | `VLM_SCENE_DESCRIPTION_OUTPUT_PATH` | `output/scene_descriptions.json` | Where to write the JSON results |
| `--max-scenes` | — | (all scenes) | Only process the first N scenes |

**Examples:**

```bash
# Full v1.0-mini run with defaults
uv run vlm_scene_description run

# Quick check against the first 2 scenes only
uv run vlm_scene_description run --max-scenes 2

# Different dataset location and camera
uv run vlm_scene_description run --dataroot /mnt/nuscenes --camera CAM_BACK
```

Each scene's output line during the run looks like:

```
  scene-0061: a busy city street with cars and pedestrians
```

---

## `test smoke`

Run the smoke test suite against a live API.

```bash
uv run vlm_scene_description test smoke [OPTIONS]
```

| Option | Env var | Default | Description |
|---|---|---|---|
| `--api-url` | `API_URL` | `http://127.0.0.1:8080` | Base URL of the running API |
| `--verbose` / `-v` | — | off | Pass `-v` to pytest |

**Examples:**

```bash
# Against the local dev server
uv run vlm_scene_description test smoke

# Against a remote target
uv run vlm_scene_description test smoke --api-url https://staging.example.com

# Via environment variable
API_URL=https://staging.example.com uv run vlm_scene_description test smoke --verbose
```

Exits with the pytest exit code. Exits `0` when all tests pass or when no smoke tests are collected yet.
