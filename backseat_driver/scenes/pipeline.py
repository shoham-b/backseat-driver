"""Orchestrates the end-to-end scene-description pipeline.

1. Load one representative keyframe per scene (SceneLoader).
2. Run each keyframe through a VLM to get a caption (Captioner).
3. Return a SceneDescription per scene, ready to be written out.

Both dependencies are abstract ports, so the pipeline is unit-testable with fakes
and never imports nuscenes-devkit, transformers, or torch directly.
"""

from collections.abc import Callable

from backseat_driver.captioning.captioner import Captioner
from backseat_driver.models import SceneDescription, SceneKeyframe
from backseat_driver.scenes.scene_loader import SceneLoader

# Called before each keyframe is captioned with (1-based index, total, keyframe).
ProgressCallback = Callable[[int, int, SceneKeyframe], None]


def describe_keyframe(keyframe: SceneKeyframe, captioner: Captioner, image_path: str) -> SceneDescription:
    """Caption the image at `image_path` as the keyframe's scene. Shared by the batch pipeline and the caption worker.

    The path to read is separate from `keyframe.image_path`, which is what the description records: a worker captions
    a local copy, but the result still names the dataset image.
    """
    return SceneDescription(
        scene_token=keyframe.scene_token,
        scene_name=keyframe.scene_name,
        camera_channel=keyframe.camera_channel,
        image_path=keyframe.image_path,
        reference_description=keyframe.reference_description,
        description=captioner.caption(image_path),
        model_name=captioner.model_name,
    )


class ScenePipeline:
    """Runs the loader → captioner pipeline over every scene in the dataset."""

    def __init__(self, loader: SceneLoader, captioner: Captioner) -> None:
        self._loader = loader
        self._captioner = captioner

    def run(self, max_scenes: int | None = None, on_progress: ProgressCallback | None = None) -> list[SceneDescription]:
        keyframes = self._loader.load_keyframes()
        if max_scenes is not None:
            # Count scenes, not keyframes: a multi-camera run has several keyframes per scene.
            kept = set(list(dict.fromkeys(k.scene_token for k in keyframes))[:max_scenes])
            keyframes = [k for k in keyframes if k.scene_token in kept]

        descriptions: list[SceneDescription] = []
        for index, keyframe in enumerate(keyframes, start=1):
            if on_progress:
                on_progress(index, len(keyframes), keyframe)
            descriptions.append(describe_keyframe(keyframe, self._captioner, keyframe.image_path))
        return descriptions
