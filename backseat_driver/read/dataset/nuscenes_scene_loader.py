"""Loads one representative keyframe image per nuScenes scene.

NuScenes stores each scene as a linked list of samples (keyframes), reachable
by walking ``sample["next"]`` tokens starting at ``scene["first_sample_token"]``.
We pick the middle sample of that chain as the "representative" frame — the
first frame is often a static lead-in, so the midpoint is more likely to show
the scene in motion.

Usage::

    loader = NuScenesSceneLoader(dataroot="data/sets/nuscenes", version="v1.0-mini", camera_channels=["CAM_FRONT"])
    keyframes = loader.load_keyframes()
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from backseat_driver.errors import NotFoundError
from backseat_driver.models import Camera, SceneKeyframe
from backseat_driver.read.dataset.nuscenes_tables import NuScenesTables
from backseat_driver.read.dataset.scene_loader import SceneLoader

ALL_CAMERA_CHANNELS = tuple(camera.channel for camera in Camera)


def open_nuscenes(version: str, dataroot: str) -> NuScenesTables:
    """Open the metadata tables; a dataroot holding only them works, so ingest never downloads an image."""
    return NuScenesTables(version, dataroot)


class NuScenesSceneLoader(SceneLoader):
    """Reads scenes from a local nuScenes dataset's metadata tables."""

    def __init__(
        self,
        dataroot: str,
        version: str = "v1.0-mini",
        camera_channels: Sequence[str] = ("CAM_FRONT",),
        open_dataset: Callable[[str, str], Any] = open_nuscenes,
    ) -> None:
        if not camera_channels:
            raise ValueError("camera_channels must name at least one camera")
        self._dataroot = dataroot
        self._version = version
        self._camera_channels = tuple(camera_channels)
        self._open_dataset = open_dataset

    def load_keyframes(self) -> list[SceneKeyframe]:
        """Return one SceneKeyframe per scene and camera, in dataset order (a scene's cameras stay together)."""
        nusc = self._open_dataset(self._version, self._dataroot)
        keyframes: list[SceneKeyframe] = []
        for scene in nusc.scene:
            sample = self._middle_sample(nusc, scene)
            for channel in self._camera_channels:
                keyframes.append(self._keyframe_for_camera(nusc, scene, sample, channel))
        return keyframes

    @staticmethod
    def _keyframe_for_camera(
        nusc: NuScenesTables, scene: dict[str, Any], sample: dict[str, Any], channel: str
    ) -> SceneKeyframe:
        sample_data_token = sample["data"].get(channel)
        if sample_data_token is None:
            raise NotFoundError(f"Scene {scene['name']!r} has no {channel} data in its middle sample")
        return SceneKeyframe(
            scene_token=scene["token"],
            scene_name=scene["name"],
            camera_channel=channel,
            image_path=nusc.get("sample_data", sample_data_token)["filename"],
            reference_description=scene.get("description") or None,
        )

    @staticmethod
    def _middle_sample(nusc: NuScenesTables, scene: dict[str, Any]) -> dict[str, Any]:
        samples: list[dict[str, Any]] = []
        token = scene["first_sample_token"]
        while token:
            sample = nusc.get("sample", token)
            samples.append(sample)
            token = sample["next"]
        return samples[len(samples) // 2]
