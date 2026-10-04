from pathlib import Path

from backseat_driver.models import SceneKeyframe
from backseat_driver.read.dataset.scene_loader import SceneLoader
from backseat_driver.read.s3.stored_scene_loader import StoredSceneLoader
from tests.fakes import FakeDatasetStore, FakeSceneLoader


def _keyframe(image_path: str) -> SceneKeyframe:
    return SceneKeyframe(scene_token="t", scene_name="scene-0001", camera_channel="CAM_FRONT", image_path=image_path)


def test_tables_of_the_version_are_downloaded_and_the_loaders_keys_are_passed_through() -> None:
    store, dataroots = FakeDatasetStore(), []

    def make_loader(dataroot: str) -> SceneLoader:
        dataroots.append(dataroot)
        return FakeSceneLoader([_keyframe("samples/CAM_FRONT/a.jpg")])

    keyframes = StoredSceneLoader(store, "v1.0-mini", make_loader).load_keyframes()

    [(prefix, directory)] = store.downloaded_prefixes
    assert prefix == "v1.0-mini/"
    assert directory == Path(dataroots[0]) / "v1.0-mini"
    assert [k.image_path for k in keyframes] == ["samples/CAM_FRONT/a.jpg"]


def test_other_keyframe_fields_are_kept() -> None:
    loader = StoredSceneLoader(
        FakeDatasetStore(), "v1.0-mini", lambda dataroot: FakeSceneLoader([_keyframe("samples/CAM_FRONT/a.jpg")])
    )

    [keyframe] = loader.load_keyframes()

    assert (keyframe.scene_token, keyframe.scene_name, keyframe.camera_channel) == ("t", "scene-0001", "CAM_FRONT")
