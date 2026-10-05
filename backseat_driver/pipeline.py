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

from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack

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
    return _describe(keyframe, captioner.caption(local_path), captioner.model_name)


def describe_keyframes(
    keyframes: Sequence[SceneKeyframe], captioner: Captioner, local_paths: Sequence[str]
) -> list[SceneDescription]:
    """`describe_keyframe` for several keyframes at once, so the captioner can run them together."""
    if len(keyframes) != len(local_paths):
        raise ValueError(f"got {len(local_paths)} local paths for {len(keyframes)} keyframes")
    captions = captioner.caption_many(local_paths)
    return [
        _describe(keyframe, caption, captioner.model_name)
        for keyframe, caption in zip(keyframes, captions, strict=True)
    ]


def _describe(keyframe: SceneKeyframe, caption: str, model_name: str) -> SceneDescription:
    return SceneDescription(
        scene_token=keyframe.scene_token,
        scene_name=keyframe.scene_name,
        camera_channel=keyframe.camera_channel,
        image_path=keyframe.image_path,
        reference_description=keyframe.reference_description,
        description=caption,
        model_name=model_name,
    )


def first_scenes(keyframes: list[SceneKeyframe], max_scenes: int | None) -> list[SceneKeyframe]:
    """The keyframes of the first `max_scenes` scenes, in their original order; all of them when `max_scenes` is None.

    Counts scenes, not keyframes: a multi-camera run has several keyframes per scene. Shared by the batch pipeline and
    the ingest worker, so `max_scenes` means the same in both.
    """
    if max_scenes is None:
        return keyframes
    kept = set(list(dict.fromkeys(k.scene_token for k in keyframes))[:max_scenes])
    return [k for k in keyframes if k.scene_token in kept]


class ScenePipeline:
    """Runs the loader → captioner pipeline over every scene in the dataset."""

    def __init__(self, loader: SceneLoader, captioner: Captioner, images: ImageStore, batch_size: int = 1) -> None:
        if batch_size < 1:
            raise ValueError(f"batch_size must be at least 1, got {batch_size}")
        self._loader = loader
        self._captioner = captioner
        self._images = images
        self._batch_size = batch_size

    def run(self, max_scenes: int | None = None, on_progress: ProgressCallback | None = None) -> list[SceneDescription]:
        """Progress is reported once per batch, with the batch's first keyframe, before the batch is captioned."""
        if max_scenes is not None and max_scenes < 1:
            raise ValueError(f"max_scenes must be at least 1, got {max_scenes}")
        # Loading the model and reading the scenes both take seconds and need nothing from each other.
        with ThreadPoolExecutor(max_workers=1) as pool:
            loading = pool.submit(self._captioner.load)
            keyframes = first_scenes(self._loader.load_keyframes(), max_scenes)
            loading.result()

        descriptions: list[SceneDescription] = []
        for start in range(0, len(keyframes), self._batch_size):
            batch = keyframes[start : start + self._batch_size]
            if on_progress:
                on_progress(start + 1, len(keyframes), batch[0])
            with ExitStack() as copies:
                local_paths = [
                    str(copies.enter_context(self._images.local_copy(self._images.uri_for(keyframe.image_path))))
                    for keyframe in batch
                ]
                descriptions.extend(describe_keyframes(batch, self._captioner, local_paths))
        return descriptions
