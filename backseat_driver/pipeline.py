"""The whole program in one place: read the scenes, process each image, write the descriptions.

    keyframes = loader.load_keyframes()                 # read    (backseat_driver.read)
    descriptions = [describe_keyframe(...) for ...]     # process (backseat_driver.process)
    write_json(descriptions, path)                      # write   (backseat_driver.write), done by the caller

`ScenePipeline` runs the first two in one process; the `describe` command adds the third. The distributed layer
splits the same steps across queues instead of changing them: `IngestWorker` is the read step, `CaptionWorker` calls
`describe_keyframe` (the process step) once per task, and the job store is the write step.

The loader and captioner are abstract ports, so the pipeline is unit-testable with fakes and never imports
nuscenes-devkit, transformers, or torch directly.
"""

from collections.abc import Callable

from backseat_driver.models import SceneDescription, SceneKeyframe
from backseat_driver.process.captioner import Captioner
from backseat_driver.read.dataset.scene_loader import SceneLoader
from backseat_driver.read.images.image_store import ImageStore

# Called before each keyframe is captioned with (1-based index, total, keyframe).
ProgressCallback = Callable[[int, int, SceneKeyframe], None]


def describe_keyframe(keyframe: SceneKeyframe, captioner: Captioner, local_path: str) -> SceneDescription:
    """Caption the file at `local_path` as the keyframe's scene. Shared by the batch pipeline and the caption worker.

    The file to read is separate from `keyframe.image_path`, which is what the description records: the image is
    captioned from a local copy, but the result still names it by its dataset key.
    """
    return SceneDescription(
        scene_token=keyframe.scene_token,
        scene_name=keyframe.scene_name,
        camera_channel=keyframe.camera_channel,
        image_path=keyframe.image_path,
        reference_description=keyframe.reference_description,
        description=captioner.caption(local_path),
        model_name=captioner.model_name,
    )


class ScenePipeline:
    """Runs the loader → captioner pipeline over every scene in the dataset."""

    def __init__(self, loader: SceneLoader, captioner: Captioner, images: ImageStore) -> None:
        self._loader = loader
        self._captioner = captioner
        self._images = images

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
            with self._images.local_copy(self._images.uri_for(keyframe.image_path)) as local_path:
                descriptions.append(describe_keyframe(keyframe, self._captioner, str(local_path)))
        return descriptions
