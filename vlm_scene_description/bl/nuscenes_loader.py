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

from typing import TYPE_CHECKING, Any, Protocol

from vlm_scene_description.models import SceneKeyframe

# NotFoundError (bl.errors) belongs in _keyframe_for_scene once implemented —
# raised when scene[self._camera_channel] is missing from the sample's data.

if TYPE_CHECKING:
    from nuscenes.nuscenes import NuScenes


class SceneLoader(Protocol):
    """Anything that can produce one representative keyframe per scene."""

    def load_keyframes(self) -> list[SceneKeyframe]: ...


class NuScenesSceneLoader:
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
        raise NotImplementedError

    @staticmethod
    def _middle_sample(nusc: "NuScenes", scene: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError
