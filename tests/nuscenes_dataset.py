"""Builds a tiny but real nuScenes dataset on disk, so tests can run the actual nuscenes-devkit over it.

Only the tables and files the devkit insists on are written; everything else is empty. Each scene has three
samples with one CAM_FRONT image, so the loader's "middle sample" choice is observable from the image name.
"""

import json
from pathlib import Path

from PIL import Image

SCENE_LABELS = ["Parked truck, construction ahead", "Night, rain, turn right"]
SAMPLES_PER_SCENE = 3
VERSION = "v1.0-mini"


def middle_image(scene_index: int) -> str:
    return f"samples/CAM_FRONT/scene{scene_index}_frame{SAMPLES_PER_SCENE // 2}.jpg"


def build_nuscenes_dataset(root: Path, scene_labels: list[str] = SCENE_LABELS) -> Path:
    version_dir = root / VERSION
    version_dir.mkdir(parents=True)
    (root / "maps").mkdir()
    Image.new("L", (10, 10)).save(root / "maps" / "map.png")

    tables: dict[str, list[dict]] = {
        name: [] for name in ("category", "attribute", "visibility", "instance", "sample_annotation")
    }
    tables["map"] = [{"token": "map", "log_tokens": ["log"], "category": "semantic_prior", "filename": "maps/map.png"}]
    tables["sensor"] = [{"token": "sensor", "channel": "CAM_FRONT", "modality": "camera"}]
    tables["calibrated_sensor"] = [
        {
            "token": "calibration",
            "sensor_token": "sensor",
            "translation": [0, 0, 0],
            "rotation": [1, 0, 0, 0],
            "camera_intrinsic": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
        }
    ]
    tables["ego_pose"] = [{"token": "ego", "timestamp": 0, "rotation": [1, 0, 0, 0], "translation": [0, 0, 0]}]
    tables["log"] = [
        {"token": "log", "logfile": "log", "vehicle": "car", "date_captured": "2026-01-01", "location": "x"}
    ]
    tables["scene"], tables["sample"], tables["sample_data"] = [], [], []

    for scene_index, label in enumerate(scene_labels):
        tokens = [f"scene{scene_index}-sample{i}" for i in range(SAMPLES_PER_SCENE)]
        tables["scene"].append(
            {
                "token": f"scene{scene_index}",
                "name": f"scene-{scene_index:04d}",
                "description": label,
                "log_token": "log",
                "nbr_samples": SAMPLES_PER_SCENE,
                "first_sample_token": tokens[0],
                "last_sample_token": tokens[-1],
            }
        )
        for i, token in enumerate(tokens):
            image = root / f"samples/CAM_FRONT/scene{scene_index}_frame{i}.jpg"
            image.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (32, 18), (40 * scene_index, 40 * i, 120)).save(image)
            tables["sample"].append(
                {
                    "token": token,
                    "timestamp": i,
                    "scene_token": f"scene{scene_index}",
                    "prev": tokens[i - 1] if i else "",
                    "next": tokens[i + 1] if i < SAMPLES_PER_SCENE - 1 else "",
                }
            )
            tables["sample_data"].append(
                {
                    "token": f"data-{token}",
                    "sample_token": token,
                    "ego_pose_token": "ego",
                    "calibrated_sensor_token": "calibration",
                    "filename": f"samples/CAM_FRONT/scene{scene_index}_frame{i}.jpg",
                    "fileformat": "jpg",
                    "is_key_frame": True,
                    "height": 18,
                    "width": 32,
                    "timestamp": i,
                    "prev": "",
                    "next": "",
                }
            )

    for name, rows in tables.items():
        (version_dir / f"{name}.json").write_text(json.dumps(rows))
    return root
