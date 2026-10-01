"""Loads one representative keyframe image per nuScenes scene.

NuScenes stores each scene as a linked list of samples (keyframes), reachable
by walking ``sample["next"]`` tokens starting at ``scene["first_sample_token"]``.
We pick the middle sample of that chain as the "representative" frame — the
first frame is often a static lead-in, so the midpoint is more likely to show
the scene in motion.

Usage::

    loader = NuScenesSceneLoader(dataroot="data/sets/nuscenes", version="v1.0-mini")
    keyframes = loader.load_keyframes()
"""

from typing import TYPE_CHECKING, Any

from backseat_driver.bl.errors import NotFoundError
from backseat_driver.bl.scene_loader import SceneLoader
from backseat_driver.models import SceneKeyframe

if TYPE_CHECKING:
    from nuscenes.nuscenes import NuScenes


class NuScenesSceneLoader(SceneLoader):
    """Reads scenes from a local nuScenes dataset via nuscenes-devkit."""

    def __init__(
        self,
        dataroot: str,
        version: str = "v1.0-mini",
        camera_channel: str = "CAM_FRONT",
    ) -> None:
        self._dataroot = dataroot
        self._version = version
        self._camera_channel = camera_channel

    def load_keyframes(self) -> list[SceneKeyframe]:
        """Return one SceneKeyframe per scene in the dataset, in dataset order."""
        from nuscenes.nuscenes import NuScenes

        nusc = NuScenes(version=self._version, dataroot=self._dataroot, verbose=False)
        return [self._keyframe_for_scene(nusc, scene) for scene in nusc.scene]

    def _keyframe_for_scene(self, nusc: "NuScenes", scene: dict[str, Any]) -> SceneKeyframe:
        sample = self._middle_sample(nusc, scene)
        sample_data_token = sample["data"].get(self._camera_channel)
        if sample_data_token is None:
            raise NotFoundError(f"Scene {scene['name']!r} has no {self._camera_channel} data in its middle sample")
        return SceneKeyframe(
            scene_token=scene["token"],
            scene_name=scene["name"],
            camera_channel=self._camera_channel,
            image_path=nusc.get_sample_data_path(sample_data_token),
            reference_description=scene.get("description") or None,
        )

    @staticmethod
    def _middle_sample(nusc: "NuScenes", scene: dict[str, Any]) -> dict[str, Any]:
        samples: list[dict[str, Any]] = []
        token = scene["first_sample_token"]
        while token:
            sample = nusc.get("sample", token)
            samples.append(sample)
            token = sample["next"]
        return samples[len(samples) // 2]
