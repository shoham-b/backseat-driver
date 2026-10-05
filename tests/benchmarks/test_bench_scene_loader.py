"""Benchmarks for keyframe selection over a synthetic nuScenes-shaped dataset.

The loader walks each scene's linked list of samples to pick the middle one. The fake
mirrors the real nuScenes v1.0-mini shape (about 40 keyframes per scene) without a
dataset on disk.
"""

from typing import Any

import pytest
from pytest_codspeed import BenchmarkFixture

from backseat_driver.read.dataset.nuscenes_scene_loader import NuScenesSceneLoader
from tests.benchmarks.loop import run

SAMPLES_PER_SCENE = 40


class _SyntheticNuScenes:
    """Stands in for nuscenes.nuscenes.NuScenes, with `scenes` scenes of `SAMPLES_PER_SCENE` samples each."""

    scenes = 10

    def __init__(self, version: str, dataroot: str, verbose: bool = False) -> None:
        self.dataroot = dataroot
        self.scene: list[dict[str, Any]] = []
        self._samples: dict[str, dict[str, Any]] = {}
        for s in range(self.scenes):
            tokens = [f"sample-{s}-{i}" for i in range(SAMPLES_PER_SCENE)]
            for i, token in enumerate(tokens):
                self._samples[token] = {
                    "token": token,
                    "data": {"CAM_FRONT": f"sd-{token}", "CAM_BACK": f"sd-back-{token}"},
                    "next": tokens[i + 1] if i + 1 < len(tokens) else "",
                }
            self.scene.append({"token": f"scene-token-{s}", "name": f"scene-{s:04d}", "first_sample_token": tokens[0]})

    def get(self, table: str, token: str) -> dict[str, Any]:
        if table == "sample_data":
            return {"filename": f"samples/CAM_FRONT/{token}.jpg"}
        return self._samples[token]


@pytest.mark.parametrize("scenes", [10, 200])
def test_load_keyframes(benchmark: BenchmarkFixture, scenes: int) -> None:
    dataset_cls = type("_Dataset", (_SyntheticNuScenes,), {"scenes": scenes})
    dataset = dataset_cls(version="v1.0-mini", dataroot="data/sets/nuscenes")
    # Build the synthetic dataset once, so only keyframe selection is measured.
    loader = NuScenesSceneLoader(
        dataroot="data/sets/nuscenes", version="v1.0-mini", open_dataset=lambda version, dataroot: dataset
    )

    keyframes = benchmark(lambda: run(loader.load_keyframes()))

    assert len(keyframes) == scenes
    assert keyframes[0].image_path.endswith(f"sd-sample-0-{SAMPLES_PER_SCENE // 2}.jpg")
