from pathlib import Path

import pytest

from backseat_driver.models import SceneKeyframe
from backseat_driver.read.s3.stored_scene_loader import StoredSceneLoader
from backseat_driver.read.scene_loader import SceneLoader
from tests.fakes import FakeDatasetStore


def _keyframe(image_path: str) -> SceneKeyframe:
    return SceneKeyframe(scene_token="t", scene_name="scene-0001", camera_channel="CAM_FRONT", image_path=image_path)


class _LoaderOverDataroot(SceneLoader):
    """Reports each image under whatever dataroot it was built for, like the devkit loader does."""

    def __init__(self, dataroot: str, relative_paths: list[str]) -> None:
        self.dataroot = dataroot
        self._relative_paths = relative_paths

    def load_keyframes(self) -> list[SceneKeyframe]:
        return [_keyframe(f"{Path(self.dataroot).as_posix()}/{path}") for path in self._relative_paths]


def test_tables_of_the_version_are_downloaded_and_images_are_reported_by_dataset_relative_key() -> None:
    store, built = FakeDatasetStore(), []

    def make_loader(dataroot: str) -> SceneLoader:
        built.append(_LoaderOverDataroot(dataroot, ["samples/CAM_FRONT/a.jpg"]))
        return built[-1]

    keyframes = StoredSceneLoader(store, "v1.0-mini", make_loader).load_keyframes()

    [(prefix, directory)] = store.downloaded_prefixes
    assert prefix == "v1.0-mini/"
    assert directory == Path(built[0].dataroot) / "v1.0-mini"
    assert [k.image_path for k in keyframes] == ["samples/CAM_FRONT/a.jpg"]


def test_other_keyframe_fields_are_kept() -> None:
    loader = StoredSceneLoader(
        FakeDatasetStore(), "v1.0-mini", lambda dataroot: _LoaderOverDataroot(dataroot, ["samples/CAM_FRONT/a.jpg"])
    )

    [keyframe] = loader.load_keyframes()

    assert (keyframe.scene_token, keyframe.scene_name, keyframe.camera_channel) == ("t", "scene-0001", "CAM_FRONT")


def test_a_keyframe_outside_the_dataroot_fails_fast() -> None:
    class _Elsewhere(SceneLoader):
        def load_keyframes(self) -> list[SceneKeyframe]:
            return [_keyframe("/somewhere/else/a.jpg")]

    loader = StoredSceneLoader(FakeDatasetStore(), "v1.0-mini", lambda dataroot: _Elsewhere())

    with pytest.raises(ValueError, match="not under the dataroot"):
        loader.load_keyframes()
