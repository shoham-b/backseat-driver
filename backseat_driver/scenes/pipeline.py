"""Orchestrates the end-to-end scene-description pipeline.

1. Load one representative keyframe per scene (SceneLoader).
2. Run each keyframe through a VLM to get a caption (Captioner).
3. Return a SceneDescription per scene, ready to be written out.

Both dependencies are abstract ports, so the pipeline is unit-testable with fakes
and never imports nuscenes-devkit, transformers, or torch directly.
"""

from loguru import logger

from backseat_driver.captioning.captioner import Captioner
from backseat_driver.models import SceneDescription, SceneKeyframe
from backseat_driver.scenes.scene_loader import SceneLoader


def describe_keyframe(keyframe: SceneKeyframe, captioner: Captioner) -> SceneDescription:
    """Caption one keyframe. Shared by the batch pipeline and the distributed caption worker."""
    return SceneDescription(
        scene_token=keyframe.scene_token,
        scene_name=keyframe.scene_name,
        camera_channel=keyframe.camera_channel,
        image_path=keyframe.image_path,
        description=captioner.caption(keyframe.image_path),
        model_name=captioner.model_name,
    )


class ScenePipeline:
    """Runs the loader → captioner pipeline over every scene in the dataset."""

    def __init__(self, loader: SceneLoader, captioner: Captioner) -> None:
        self._loader = loader
        self._captioner = captioner

    def run(self, max_scenes: int | None = None) -> list[SceneDescription]:
        keyframes = self._loader.load_keyframes()
        if max_scenes is not None:
            keyframes = keyframes[:max_scenes]

        descriptions: list[SceneDescription] = []
        for keyframe in keyframes:
            logger.bind(scene=keyframe.scene_name).info("describing scene")
            descriptions.append(describe_keyframe(keyframe, self._captioner))
        return descriptions
