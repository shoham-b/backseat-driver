"""Reports a loader's keyframes by dataset-relative key instead of by filesystem path.

The devkit loader names images by their path under whatever dataroot it was given. The job flow addresses an image by
its key below the dataroot (`samples/CAM_FRONT/<name>.jpg`) so the same string means the same image whether the dataset
is on a local disk or in a bucket.
"""

from pathlib import Path

from backseat_driver.models import SceneKeyframe
from backseat_driver.read.scene_loader import SceneLoader


class RelativeSceneLoader(SceneLoader):
    def __init__(self, loader: SceneLoader, dataroot: str) -> None:
        self._loader = loader
        self._root = Path(dataroot).as_posix().rstrip("/") + "/"

    def load_keyframes(self) -> list[SceneKeyframe]:
        return [self._relative(keyframe) for keyframe in self._loader.load_keyframes()]

    def _relative(self, keyframe: SceneKeyframe) -> SceneKeyframe:
        image_path = keyframe.image_path.replace("\\", "/")
        if not image_path.startswith(self._root):
            raise ValueError(f"Keyframe image {image_path!r} is not under the dataroot {self._root!r}")
        return keyframe.model_copy(update={"image_path": image_path.removeprefix(self._root)})
