from typing import Any

import pytest

from backseat_driver.errors import NotFoundError
from backseat_driver.scenes.nuscenes_scene_loader import NuScenesSceneLoader


class _FakeNuScenes:
    """Stands in for nuscenes.nuscenes.NuScenes — no real dataset on disk."""

    def __init__(self, version: str, dataroot: str, verbose: bool = False) -> None:
        self.version = version
        self.dataroot = dataroot
        self.scene: list[dict[str, Any]] = [
            {
                "token": "scene-token-1",
                "name": "scene-0001",
                "first_sample_token": "sample-1",
                "nbr_samples": 3,
            }
        ]
        self._samples: dict[str, dict[str, Any]] = {
            "sample-1": {"token": "sample-1", "data": {"CAM_FRONT": "sd-1"}, "next": "sample-2"},
            "sample-2": {"token": "sample-2", "data": {"CAM_FRONT": "sd-2"}, "next": "sample-3"},
            "sample-3": {"token": "sample-3", "data": {"CAM_FRONT": "sd-3"}, "next": ""},
        }

    def get(self, table: str, token: str) -> dict[str, Any]:
        assert table == "sample"
        return self._samples[token]

    def get_sample_data_path(self, sample_data_token: str) -> str:
        return f"/data/sets/nuscenes/samples/CAM_FRONT/{sample_data_token}.jpg"


@pytest.fixture(autouse=True)
def fake_nuscenes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("nuscenes.nuscenes.NuScenes", _FakeNuScenes)


def test_load_keyframes_picks_the_middle_sample() -> None:
    loader = NuScenesSceneLoader(dataroot="data/sets/nuscenes", version="v1.0-mini")

    [keyframe] = loader.load_keyframes()

    assert keyframe.scene_token == "scene-token-1"
    assert keyframe.scene_name == "scene-0001"
    assert keyframe.camera_channel == "CAM_FRONT"
    assert keyframe.image_path == "/data/sets/nuscenes/samples/CAM_FRONT/sd-2.jpg"


def test_load_keyframes_uses_configured_camera_channel() -> None:
    loader = NuScenesSceneLoader(dataroot="data/sets/nuscenes", version="v1.0-mini", camera_channel="CAM_BACK")

    with pytest.raises(NotFoundError, match="CAM_BACK"):
        loader.load_keyframes()
