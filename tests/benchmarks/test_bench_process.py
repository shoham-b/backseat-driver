"""Benchmarks for what the backends do around the model: decoding images and building requests.

The model itself is faked (a pipeline factory that returns canned text, an HTTP client that records posts), so these
track the per-image work this repository owns, which batching multiplies.
"""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from PIL import Image
from pytest_codspeed import BenchmarkFixture

from backseat_driver.process.backends.anthropic import AnthropicBackend
from backseat_driver.process.backends.huggingface import HuggingFaceBackend
from backseat_driver.process.model import CaptionModel
from backseat_driver.read.dataset.nuscenes_tables import NuScenesTables
from tests.fakes import FakeAsyncHttpClient, FakeHttpClient

BATCH_SIZES = [1, 8, 32]
# nuScenes front-camera frames are 1600x900 JPEGs.
FRAME_SIZE = (1600, 900)
CHANNELS = ("CAM_FRONT", "CAM_FRONT_LEFT", "CAM_FRONT_RIGHT", "CAM_BACK", "CAM_BACK_LEFT", "CAM_BACK_RIGHT")


@pytest.fixture(scope="module")
def frames(tmp_path_factory: pytest.TempPathFactory) -> list[str]:
    directory = tmp_path_factory.mktemp("frames")
    paths = []
    for n in range(max(BATCH_SIZES)):
        path = directory / f"frame{n}.jpg"
        Image.new("RGB", FRAME_SIZE, color=(n, 80, 120)).save(path)
        paths.append(str(path))
    return paths


def _canned_pipeline(model_name: str) -> Callable[..., Any]:
    def run(images: Any, batch_size: int | None = None) -> Any:
        caption = [{"generated_text": "a street"}]
        return [caption for _ in images] if isinstance(images, list) else caption

    return run


@pytest.mark.parametrize("batch_size", BATCH_SIZES)
def test_huggingface_generate_many(benchmark: BenchmarkFixture, frames: list[str], batch_size: int) -> None:
    backend = HuggingFaceBackend(_canned_pipeline)
    model = CaptionModel("bench/model")
    backend.load(model)

    descriptions = benchmark(backend.generate_many, frames[:batch_size], model)

    assert descriptions == ["a street"] * batch_size


@pytest.mark.parametrize("batch_size", BATCH_SIZES)
def test_anthropic_generate_many(benchmark: BenchmarkFixture, frames: list[str], batch_size: int) -> None:
    http = FakeHttpClient(response={"content": [{"type": "text", "text": "a street"}]})
    backend = AnthropicBackend(http, FakeAsyncHttpClient(http), api_key="bench")
    model = CaptionModel("claude-bench", prompt="describe")

    descriptions = benchmark(backend.generate_many, frames[:batch_size], model)

    assert descriptions[0] == "a street"


@pytest.mark.parametrize("scenes", [10, 850])
def test_read_nuscenes_tables(benchmark: BenchmarkFixture, tmp_path: Path, scenes: int) -> None:
    """Parse and index the three tables from JSON: 850 scenes is the full dataset, v1.0-mini has 10."""
    version = "v1.0-mini"
    _write_tables(tmp_path / version, scenes, samples_per_scene=40)

    def read() -> NuScenesTables:
        tables = NuScenesTables(version, str(tmp_path))
        tables.get("sample", "sample-0-0")
        tables.get("sample_data", "sd-CAM_FRONT-sample-0-0")
        return tables

    tables = benchmark(read)

    assert len(tables.scene) == scenes


def _write_tables(directory: Path, scenes: int, samples_per_scene: int) -> None:
    directory.mkdir(parents=True)
    scene_rows, sample_rows, sample_data_rows = [], [], []
    for s in range(scenes):
        tokens = [f"sample-{s}-{i}" for i in range(samples_per_scene)]
        scene_rows.append({"token": f"scene-{s}", "name": f"scene-{s:04d}", "first_sample_token": tokens[0]})
        for i, token in enumerate(tokens):
            sample_rows.append({"token": token, "next": tokens[i + 1] if i + 1 < len(tokens) else ""})
            # The real tables hold six cameras of key frames per sample (plus sweeps, which are not modelled here).
            for channel in CHANNELS:
                sample_data_rows.append(
                    {
                        "token": f"sd-{channel}-{token}",
                        "sample_token": token,
                        "calibrated_sensor_token": f"calibration-{channel}",
                        "is_key_frame": True,
                        "filename": f"samples/{channel}/{token}.jpg",
                    }
                )
    sensor_rows = [{"token": f"sensor-{channel}", "channel": channel} for channel in CHANNELS]
    calibrated_rows = [{"token": f"calibration-{channel}", "sensor_token": f"sensor-{channel}"} for channel in CHANNELS]
    tables = {
        "scene": scene_rows,
        "sample": sample_rows,
        "sample_data": sample_data_rows,
        "sensor": sensor_rows,
        "calibrated_sensor": calibrated_rows,
    }
    for name, rows in tables.items():
        (directory / f"{name}.json").write_text(json.dumps(rows))
