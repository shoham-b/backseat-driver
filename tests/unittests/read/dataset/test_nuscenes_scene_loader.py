import asyncio
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from backseat_driver.errors import NotFoundError
from backseat_driver.read.dataset.nuscenes_scene_loader import ALL_CAMERA_CHANNELS, NuScenesSceneLoader


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
    """Dataset layout is given as scene name -> number of samples."""

    def __init__(self, layout: dict[str, int], channels: tuple[str, ...] = ("CAM_FRONT",)) -> None:
        self.scene = [
            {
                "token": f"{name}-token",
                "name": name,
                "first_sample_token": f"{name}-s0",
                "description": f"label of {name}",
            }
            for name in layout
        ]
        self._samples: dict[str, dict[str, Any]] = {}
        for name, length in layout.items():
            self._samples |= _chain(name, length, channels)

    def get(self, table: str, token: str) -> dict[str, Any]:
        if table == "sample_data":
            return {"filename": f"samples/{token}.jpg"}
        assert table == "sample"
        return self._samples[token]


class _FakeDevkit:
    """Stands in for `open_nuscenes`: serves `layout` and records every (version, dataroot) it was asked to open."""

    def __init__(self, layout: dict[str, int] | None = None, channels: tuple[str, ...] = ("CAM_FRONT",)) -> None:
        self.opened: list[tuple[str, str]] = []
        self._layout = layout or {}
        self._channels = channels

    def __call__(self, version: str, dataroot: str) -> _FakeNuScenes:
        self.opened.append((version, dataroot))
        return _FakeNuScenes(self._layout, self._channels)


async def test_empty_dataset_yields_no_keyframes() -> None:
    assert await NuScenesSceneLoader(dataroot="d", open_dataset=_FakeDevkit()).load_keyframes() == []


@pytest.mark.parametrize(("length", "middle"), [(1, 0), (2, 1), (3, 1), (4, 2), (40, 20)])
async def test_middle_sample_of_a_chain(length: int, middle: int) -> None:
    loader = NuScenesSceneLoader(dataroot="d", open_dataset=_FakeDevkit({"scene-0001": length}))

    [keyframe] = await loader.load_keyframes()

    assert keyframe.image_path == f"samples/scene-0001-CAM_FRONT-sd{middle}.jpg"


@given(length=st.integers(min_value=1, max_value=200))
def test_property_the_picked_sample_is_always_index_len_div_2(length: int) -> None:
    loader = NuScenesSceneLoader(dataroot="d", open_dataset=_FakeDevkit({"s": length}))

    [keyframe] = asyncio.run(loader.load_keyframes())  # hypothesis cannot drive a coroutine test

    assert keyframe.image_path == f"samples/s-CAM_FRONT-sd{length // 2}.jpg"


async def test_a_keyframe_carries_the_scene_identity_and_its_nuscenes_label() -> None:
    loader = NuScenesSceneLoader(dataroot="d", open_dataset=_FakeDevkit({"scene-0001": 3}))

    [keyframe] = await loader.load_keyframes()

    assert (keyframe.scene_token, keyframe.scene_name, keyframe.camera_channel) == (
        "scene-0001-token",
        "scene-0001",
        "CAM_FRONT",
    )
    assert keyframe.reference_description == "label of scene-0001"


async def test_keyframes_keep_dataset_order_across_scenes() -> None:
    devkit = _FakeDevkit({"scene-b": 3, "scene-a": 1, "scene-c": 2})

    keyframes = await NuScenesSceneLoader(dataroot="d", open_dataset=devkit).load_keyframes()

    assert [k.scene_name for k in keyframes] == ["scene-b", "scene-a", "scene-c"]
    assert [k.scene_token for k in keyframes] == ["scene-b-token", "scene-a-token", "scene-c-token"]


async def test_dataroot_and_version_reach_the_devkit() -> None:
    devkit = _FakeDevkit({"s": 1})

    await NuScenesSceneLoader(dataroot="/some/root", version="v1.0-trainval", open_dataset=devkit).load_keyframes()

    assert devkit.opened == [("v1.0-trainval", "/some/root")]


async def test_constructing_the_loader_never_touches_the_dataset() -> None:
    devkit = _FakeDevkit()

    NuScenesSceneLoader(dataroot="/does/not/exist", open_dataset=devkit)

    assert devkit.opened == []


async def test_loading_twice_rereads_the_dataset() -> None:
    devkit = _FakeDevkit({"s": 1})
    loader = NuScenesSceneLoader(dataroot="d", open_dataset=devkit)

    assert await loader.load_keyframes() == await loader.load_keyframes()
    assert len(devkit.opened) == 2


async def test_a_scene_without_the_camera_names_the_scene_and_channel() -> None:
    loader = NuScenesSceneLoader(
        dataroot="d", camera_channels=["CAM_LEFT"], open_dataset=_FakeDevkit({"scene-0042": 2})
    )

    with pytest.raises(NotFoundError, match=r"scene-0042.*CAM_LEFT"):
        await loader.load_keyframes()


async def test_every_requested_camera_yields_a_keyframe_per_scene_grouped_by_scene() -> None:
    devkit = _FakeDevkit({"scene-a": 3, "scene-b": 1}, channels=("CAM_FRONT", "CAM_BACK"))

    keyframes = await NuScenesSceneLoader(
        dataroot="d", camera_channels=["CAM_BACK", "CAM_FRONT"], open_dataset=devkit
    ).load_keyframes()

    assert [(k.scene_name, k.camera_channel) for k in keyframes] == [
        ("scene-a", "CAM_BACK"),
        ("scene-a", "CAM_FRONT"),
        ("scene-b", "CAM_BACK"),
        ("scene-b", "CAM_FRONT"),
    ]
    assert keyframes[0].image_path == "samples/scene-a-CAM_BACK-sd1.jpg"


async def test_all_camera_channels_are_the_six_nuscenes_cameras() -> None:
    assert len(set(ALL_CAMERA_CHANNELS)) == 6
    assert all(channel.startswith("CAM_") for channel in ALL_CAMERA_CHANNELS)


async def test_a_loader_without_cameras_is_rejected() -> None:
    with pytest.raises(ValueError, match="at least one camera"):
        NuScenesSceneLoader(dataroot="d", camera_channels=[])
