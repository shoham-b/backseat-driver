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

import json
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

from backseat_driver.errors import NotFoundError
from backseat_driver.models import SceneKeyframe
from backseat_driver.scenes.scene_loader import SceneLoader

if TYPE_CHECKING:
    from nuscenes.nuscenes import NuScenes


# The six cameras on a nuScenes vehicle, front-centre first then clockwise.
ALL_CAMERA_CHANNELS = ("CAM_FRONT", "CAM_FRONT_RIGHT", "CAM_BACK_RIGHT", "CAM_BACK", "CAM_BACK_LEFT", "CAM_FRONT_LEFT")


def open_nuscenes(version: str, dataroot: str) -> NuScenes:
    """Open the dataset with the devkit; it is imported here, not at module scope, as it is heavy."""
    from nuscenes.nuscenes import NuScenes

    return NuScenes(version=version, dataroot=dataroot, verbose=False)


def open_nuscenes_tables(version: str, dataroot: str) -> NuScenes:
    """Open a dataroot that holds only the metadata tables, for finding keyframes without downloading any image.

    The devkit insists that every map file named in `map.json` exists when it opens the dataset, though it only reads
    them on demand. Empty placeholders satisfy it, which spares ingest the (large) maps.
    """
    root = Path(dataroot)
    for record in json.loads((root / version / "map.json").read_text()):
        placeholder = root / record["filename"]
        placeholder.parent.mkdir(parents=True, exist_ok=True)
        placeholder.touch()
    return open_nuscenes(version, dataroot)


class NuScenesSceneLoader(SceneLoader):
    """Reads scenes from a local nuScenes dataset via nuscenes-devkit."""

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
        nusc: NuScenes, scene: dict[str, Any], sample: dict[str, Any], channel: str
    ) -> SceneKeyframe:
        sample_data_token = sample["data"].get(channel)
        if sample_data_token is None:
            raise NotFoundError(f"Scene {scene['name']!r} has no {channel} data in its middle sample")
        return SceneKeyframe(
            scene_token=scene["token"],
            scene_name=scene["name"],
            camera_channel=channel,
            # The devkit joins with os.sep but its table paths use "/"; normalise so the JSON is portable across OSes.
            image_path=nusc.get_sample_data_path(sample_data_token).replace("\\", "/"),
            reference_description=scene.get("description") or None,
        )

    @staticmethod
    def _middle_sample(nusc: NuScenes, scene: dict[str, Any]) -> dict[str, Any]:
        samples: list[dict[str, Any]] = []
        token = scene["first_sample_token"]
        while token:
            sample = nusc.get("sample", token)
            samples.append(sample)
            token = sample["next"]
        return samples[len(samples) // 2]
