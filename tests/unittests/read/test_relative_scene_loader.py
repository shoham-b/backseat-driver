import pytest

from backseat_driver.models import SceneKeyframe
from backseat_driver.read.relative_scene_loader import RelativeSceneLoader
from tests.fakes import FakeSceneLoader


def _keyframe(image_path: str) -> SceneKeyframe:
    return SceneKeyframe(scene_token="t", scene_name="s", camera_channel="CAM_FRONT", image_path=image_path)


def test_images_are_reported_by_their_key_below_the_dataroot() -> None:
    loader = RelativeSceneLoader(FakeSceneLoader([_keyframe("data/sets/nu/samples/CAM_FRONT/a.jpg")]), "data/sets/nu")

    [keyframe] = loader.load_keyframes()

    assert keyframe.image_path == "samples/CAM_FRONT/a.jpg"


def test_backslashes_and_a_trailing_slash_on_the_dataroot_are_tolerated() -> None:
    loader = RelativeSceneLoader(FakeSceneLoader([_keyframe("data\\nu\\samples/CAM_FRONT/a.jpg")]), "data/nu/")

    [keyframe] = loader.load_keyframes()

    assert keyframe.image_path == "samples/CAM_FRONT/a.jpg"


def test_the_other_fields_are_kept() -> None:
    [keyframe] = RelativeSceneLoader(FakeSceneLoader([_keyframe("nu/samples/a.jpg")]), "nu").load_keyframes()

    assert (keyframe.scene_token, keyframe.scene_name, keyframe.camera_channel) == ("t", "s", "CAM_FRONT")


def test_an_image_outside_the_dataroot_fails_fast() -> None:
    loader = RelativeSceneLoader(FakeSceneLoader([_keyframe("/elsewhere/a.jpg")]), "data/nu")

    with pytest.raises(ValueError, match="not under the dataroot"):
        loader.load_keyframes()
