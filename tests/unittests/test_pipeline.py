from backseat_driver.models import SceneKeyframe
from backseat_driver.scenes.pipeline import ScenePipeline
from tests.fakes import FakeCaptioner, FakeSceneLoader


def _keyframe(n: int) -> SceneKeyframe:
    return SceneKeyframe(
        scene_token=f"token-{n}",
        scene_name=f"scene-{n}",
        camera_channel="CAM_FRONT",
        image_path=f"/data/scene-{n}.jpg",
    )


def test_run_describes_every_scene() -> None:
    keyframes = [_keyframe(1), _keyframe(2), _keyframe(3)]
    captioner = FakeCaptioner()
    pipeline = ScenePipeline(loader=FakeSceneLoader(keyframes), captioner=captioner)

    descriptions = pipeline.run()

    assert len(descriptions) == 3
    assert [d.scene_name for d in descriptions] == ["scene-1", "scene-2", "scene-3"]
    assert all(d.model_name == "fake-model" for d in descriptions)
    assert captioner.seen_paths == [kf.image_path for kf in keyframes]


def test_run_respects_max_scenes() -> None:
    keyframes = [_keyframe(1), _keyframe(2), _keyframe(3)]
    pipeline = ScenePipeline(loader=FakeSceneLoader(keyframes), captioner=FakeCaptioner())

    descriptions = pipeline.run(max_scenes=2)

    assert len(descriptions) == 2
    assert [d.scene_name for d in descriptions] == ["scene-1", "scene-2"]


def test_run_on_empty_dataset_returns_empty_list() -> None:
    pipeline = ScenePipeline(loader=FakeSceneLoader([]), captioner=FakeCaptioner())

    descriptions = pipeline.run()

    assert descriptions == []


def test_description_carries_keyframe_fields_through() -> None:
    keyframe = _keyframe(1)
    pipeline = ScenePipeline(loader=FakeSceneLoader([keyframe]), captioner=FakeCaptioner())

    [description] = pipeline.run()

    assert description.scene_token == keyframe.scene_token
    assert description.camera_channel == keyframe.camera_channel
    assert description.image_path == keyframe.image_path
    assert description.description == f"a caption for {keyframe.image_path}"


def test_max_scenes_counts_scenes_not_cameras() -> None:
    keyframes = [
        _keyframe(1).model_copy(update={"camera_channel": channel}) for channel in ("CAM_FRONT", "CAM_BACK")
    ] + [_keyframe(2), _keyframe(3)]
    pipeline = ScenePipeline(loader=FakeSceneLoader(keyframes), captioner=FakeCaptioner())

    descriptions = pipeline.run(max_scenes=2)

    assert [(d.scene_name, d.camera_channel) for d in descriptions] == [
        ("scene-1", "CAM_FRONT"),
        ("scene-1", "CAM_BACK"),
        ("scene-2", "CAM_FRONT"),
    ]
