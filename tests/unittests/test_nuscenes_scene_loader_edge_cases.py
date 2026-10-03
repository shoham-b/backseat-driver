from typing import Any, ClassVar

import pytest
from hypothesis import given
from hypothesis import strategies as st

from backseat_driver.errors import NotFoundError
from backseat_driver.scenes.nuscenes_scene_loader import ALL_CAMERA_CHANNELS, NuScenesSceneLoader


def _chain(scene: str, length: int, channels: tuple[str, ...]) -> dict[str, dict[str, Any]]:
    return {
        f"{scene}-s{i}": {
            "token": f"{scene}-s{i}",
            "data": {channel: f"{scene}-{channel}-sd{i}" for channel in channels},
            "next": f"{scene}-s{i + 1}" if i + 1 < length else "",
        }
        for i in range(length)
    }


class _FakeNuScenes:
    """Dataset layout is injected through `layout` (scene name -> number of samples)."""

    layout: ClassVar[dict[str, int]] = {}
    channels: ClassVar[tuple[str, ...]] = ("CAM_FRONT",)
    constructed_with: ClassVar[dict[str, Any]] = {}

    def __init__(self, version: str, dataroot: str, verbose: bool = False) -> None:
        type(self).constructed_with = {"version": version, "dataroot": dataroot, "verbose": verbose}
        self.scene = [
            {"token": f"{name}-token", "name": name, "first_sample_token": f"{name}-s0"} for name in self.layout
        ]
        self._samples: dict[str, dict[str, Any]] = {}
        for name, length in self.layout.items():
            self._samples |= _chain(name, length, self.channels)

    def get(self, table: str, token: str) -> dict[str, Any]:
        assert table == "sample"
        return self._samples[token]

    def get_sample_data_path(self, sample_data_token: str) -> str:
        return f"/samples/{sample_data_token}.jpg"


@pytest.fixture(autouse=True)
def _fake_nuscenes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("nuscenes.nuscenes.NuScenes", _FakeNuScenes)
    monkeypatch.setattr(_FakeNuScenes, "layout", {})
    monkeypatch.setattr(_FakeNuScenes, "channels", ("CAM_FRONT",))


def test_empty_dataset_yields_no_keyframes(monkeypatch: pytest.MonkeyPatch) -> None:
    assert NuScenesSceneLoader(dataroot="d").load_keyframes() == []


@pytest.mark.parametrize(("length", "middle"), [(1, 0), (2, 1), (3, 1), (4, 2), (40, 20)])
def test_middle_sample_of_a_chain(monkeypatch: pytest.MonkeyPatch, length: int, middle: int) -> None:
    monkeypatch.setattr(_FakeNuScenes, "layout", {"scene-0001": length})

    [keyframe] = NuScenesSceneLoader(dataroot="d").load_keyframes()

    assert keyframe.image_path == f"/samples/scene-0001-CAM_FRONT-sd{middle}.jpg"


@given(length=st.integers(min_value=1, max_value=200))
def test_property_the_picked_sample_is_always_index_len_div_2(length: int) -> None:
    _FakeNuScenes.layout = {"s": length}

    [keyframe] = NuScenesSceneLoader(dataroot="d").load_keyframes()

    assert keyframe.image_path == f"/samples/s-CAM_FRONT-sd{length // 2}.jpg"


def test_keyframes_keep_dataset_order_across_scenes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_FakeNuScenes, "layout", {"scene-b": 3, "scene-a": 1, "scene-c": 2})

    keyframes = NuScenesSceneLoader(dataroot="d").load_keyframes()

    assert [k.scene_name for k in keyframes] == ["scene-b", "scene-a", "scene-c"]
    assert [k.scene_token for k in keyframes] == ["scene-b-token", "scene-a-token", "scene-c-token"]


def test_dataroot_and_version_reach_the_devkit_quietly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_FakeNuScenes, "layout", {"s": 1})

    NuScenesSceneLoader(dataroot="/some/root", version="v1.0-trainval").load_keyframes()

    assert _FakeNuScenes.constructed_with == {"version": "v1.0-trainval", "dataroot": "/some/root", "verbose": False}


def test_constructing_the_loader_never_touches_the_dataset(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeNuScenes.constructed_with = {}

    NuScenesSceneLoader(dataroot="/does/not/exist")

    assert _FakeNuScenes.constructed_with == {}


def test_loading_twice_rereads_the_dataset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_FakeNuScenes, "layout", {"s": 1})
    loader = NuScenesSceneLoader(dataroot="d")

    assert loader.load_keyframes() == loader.load_keyframes()


def test_a_scene_without_the_camera_names_the_scene_and_channel(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_FakeNuScenes, "layout", {"scene-0042": 2})

    with pytest.raises(NotFoundError, match=r"scene-0042.*CAM_LEFT"):
        NuScenesSceneLoader(dataroot="d", camera_channels=["CAM_LEFT"]).load_keyframes()


def test_every_requested_camera_yields_a_keyframe_per_scene_grouped_by_scene(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_FakeNuScenes, "layout", {"scene-a": 3, "scene-b": 1})
    monkeypatch.setattr(_FakeNuScenes, "channels", ("CAM_FRONT", "CAM_BACK"))

    keyframes = NuScenesSceneLoader(dataroot="d", camera_channels=["CAM_BACK", "CAM_FRONT"]).load_keyframes()

    assert [(k.scene_name, k.camera_channel) for k in keyframes] == [
        ("scene-a", "CAM_BACK"),
        ("scene-a", "CAM_FRONT"),
        ("scene-b", "CAM_BACK"),
        ("scene-b", "CAM_FRONT"),
    ]
    assert keyframes[0].image_path == "/samples/scene-a-CAM_BACK-sd1.jpg"


def test_all_camera_channels_are_the_six_nuscenes_cameras() -> None:
    assert len(set(ALL_CAMERA_CHANNELS)) == 6
    assert all(channel.startswith("CAM_") for channel in ALL_CAMERA_CHANNELS)


def test_a_loader_without_cameras_is_rejected() -> None:
    with pytest.raises(ValueError, match="at least one camera"):
        NuScenesSceneLoader(dataroot="d", camera_channels=[])
