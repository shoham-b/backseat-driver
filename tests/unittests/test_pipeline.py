from vlm_scene_description.bl.pipeline import ScenePipeline
from vlm_scene_description.models import SceneKeyframe


class _FakeLoader:
    def __init__(self, keyframes: list[SceneKeyframe]) -> None:
        self._keyframes = keyframes

    def load_keyframes(self) -> list[SceneKeyframe]:
        return self._keyframes


class _FakeCaptioner:
    model_name = "fake-model"

    def __init__(self) -> None:
        self.seen_paths: list[str] = []

    def load(self) -> None:
        return None

    def caption(self, image_path: str) -> str:
        self.seen_paths.append(image_path)
        return f"a caption for {image_path}"

    def healthcheck(self) -> bool:
        return True


def _keyframe(n: int) -> SceneKeyframe:
    return SceneKeyframe(
        scene_token=f"token-{n}",
        scene_name=f"scene-{n}",
        camera_channel="CAM_FRONT",
        image_path=f"/data/scene-{n}.jpg",
    )


def test_run_describes_every_scene() -> None:
    keyframes = [_keyframe(1), _keyframe(2), _keyframe(3)]
    captioner = _FakeCaptioner()
    pipeline = ScenePipeline(loader=_FakeLoader(keyframes), captioner=captioner)

    descriptions = pipeline.run()

    assert len(descriptions) == 3
    assert [d.scene_name for d in descriptions] == ["scene-1", "scene-2", "scene-3"]
    assert all(d.model_name == "fake-model" for d in descriptions)
    assert captioner.seen_paths == [kf.image_path for kf in keyframes]


def test_run_respects_max_scenes() -> None:
    keyframes = [_keyframe(1), _keyframe(2), _keyframe(3)]
    pipeline = ScenePipeline(loader=_FakeLoader(keyframes), captioner=_FakeCaptioner())

    descriptions = pipeline.run(max_scenes=2)

    assert len(descriptions) == 2
    assert [d.scene_name for d in descriptions] == ["scene-1", "scene-2"]


def test_run_on_empty_dataset_returns_empty_list() -> None:
    pipeline = ScenePipeline(loader=_FakeLoader([]), captioner=_FakeCaptioner())

    descriptions = pipeline.run()

    assert descriptions == []


def test_description_carries_keyframe_fields_through() -> None:
    keyframe = _keyframe(1)
    pipeline = ScenePipeline(loader=_FakeLoader([keyframe]), captioner=_FakeCaptioner())

    [description] = pipeline.run()

    assert description.scene_token == keyframe.scene_token
    assert description.camera_channel == keyframe.camera_channel
    assert description.image_path == keyframe.image_path
    assert description.description == f"a caption for {keyframe.image_path}"
