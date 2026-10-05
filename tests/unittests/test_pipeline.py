from pathlib import Path

import pytest

from backseat_driver.models import SceneKeyframe
from backseat_driver.pipeline import ScenePipeline
from tests.fakes import FakeCaptioner, FakeImageStore, FakeSceneLoader


def _keyframe(n: int) -> SceneKeyframe:
    return SceneKeyframe(
        scene_token=f"token-{n}",
        scene_name=f"scene-{n}",
        camera_channel="CAM_FRONT",
        image_path=f"samples/CAM_FRONT/scene-{n}.jpg",
    )


def test_run_describes_every_scene() -> None:
    keyframes = [_keyframe(1), _keyframe(2), _keyframe(3)]
    captioner = FakeCaptioner()
    pipeline = ScenePipeline(loader=FakeSceneLoader(keyframes), captioner=captioner, images=FakeImageStore())

    descriptions = pipeline.run()

    assert len(descriptions) == 3
    assert [d.scene_name for d in descriptions] == ["scene-1", "scene-2", "scene-3"]
    assert all(d.model_name == "fake-model" for d in descriptions)
    assert captioner.seen_paths == [str(Path("/fetched") / f"scene-{n}.jpg") for n in (1, 2, 3)]


def test_run_respects_max_scenes() -> None:
    keyframes = [_keyframe(1), _keyframe(2), _keyframe(3)]
    pipeline = ScenePipeline(loader=FakeSceneLoader(keyframes), captioner=FakeCaptioner(), images=FakeImageStore())

    descriptions = pipeline.run(max_scenes=2)

    assert len(descriptions) == 2
    assert [d.scene_name for d in descriptions] == ["scene-1", "scene-2"]


@pytest.mark.parametrize("max_scenes", [0, -1])
def test_run_rejects_a_max_scenes_below_one_instead_of_slicing(max_scenes: int) -> None:
    keyframes = [_keyframe(1), _keyframe(2), _keyframe(3)]
    captioner = FakeCaptioner()
    pipeline = ScenePipeline(loader=FakeSceneLoader(keyframes), captioner=captioner, images=FakeImageStore())

    with pytest.raises(ValueError, match="max_scenes must be at least 1"):
        pipeline.run(max_scenes=max_scenes)

    assert captioner.seen_paths == []


def test_run_on_empty_dataset_returns_empty_list() -> None:
    pipeline = ScenePipeline(loader=FakeSceneLoader([]), captioner=FakeCaptioner(), images=FakeImageStore())

    descriptions = pipeline.run()

    assert descriptions == []


def test_description_carries_keyframe_fields_through() -> None:
    keyframe = _keyframe(1)
    pipeline = ScenePipeline(loader=FakeSceneLoader([keyframe]), captioner=FakeCaptioner(), images=FakeImageStore())

    [description] = pipeline.run()

    assert description.scene_token == keyframe.scene_token
    assert description.camera_channel == keyframe.camera_channel
    assert description.image_path == keyframe.image_path
    assert description.description == f"a caption for {Path('/fetched') / 'scene-1.jpg'}"


def test_max_scenes_counts_scenes_not_cameras() -> None:
    keyframes = [
        _keyframe(1).model_copy(update={"camera_channel": channel}) for channel in ("CAM_FRONT", "CAM_BACK")
    ] + [_keyframe(2), _keyframe(3)]
    pipeline = ScenePipeline(loader=FakeSceneLoader(keyframes), captioner=FakeCaptioner(), images=FakeImageStore())

    descriptions = pipeline.run(max_scenes=2)

    assert [(d.scene_name, d.camera_channel) for d in descriptions] == [
        ("scene-1", "CAM_FRONT"),
        ("scene-1", "CAM_BACK"),
        ("scene-2", "CAM_FRONT"),
    ]


def test_run_reports_progress_before_each_keyframe() -> None:
    keyframes = [_keyframe(1), _keyframe(2)]
    pipeline = ScenePipeline(loader=FakeSceneLoader(keyframes), captioner=FakeCaptioner(), images=FakeImageStore())
    seen: list[tuple[int, int, str]] = []

    pipeline.run(on_progress=lambda index, total, kf: seen.append((index, total, kf.scene_name)))

    assert seen == [(1, 2, "scene-1"), (2, 2, "scene-2")]


def test_run_captions_a_local_copy_of_each_image_and_releases_it() -> None:
    keyframes = [_keyframe(1), _keyframe(2)]
    images = FakeImageStore()
    pipeline = ScenePipeline(loader=FakeSceneLoader(keyframes), captioner=FakeCaptioner(), images=images)

    pipeline.run()

    expected = [f"fake://samples/CAM_FRONT/scene-{n}.jpg" for n in (1, 2)]
    assert images.opened == expected
    assert images.released == expected


class _FailingCaptioner(FakeCaptioner):
    def caption(self, image_path: str) -> str:
        raise RuntimeError("model exploded")


def test_run_propagates_a_captioning_failure_and_still_releases_the_local_copy() -> None:
    images = FakeImageStore()
    pipeline = ScenePipeline(loader=FakeSceneLoader([_keyframe(1)]), captioner=_FailingCaptioner(), images=images)

    with pytest.raises(RuntimeError, match="model exploded"):
        pipeline.run()

    assert images.released == images.opened == ["fake://samples/CAM_FRONT/scene-1.jpg"]
