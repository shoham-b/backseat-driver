"""CodSpeed benchmarks for the pure-Python parts of the pipeline.

Skipped when pytest-codspeed isn't installed (it's only installed in the CodSpeed workflow),
so the regular test run is unaffected. The model is faked: we measure our own overhead, not inference.

`@pytest.mark.benchmark` times the whole test body, so anything that isn't the code under test
is built in a fixture instead.
"""

from pathlib import Path

import pytest

from backseat_driver.bl.pipeline import ScenePipeline, describe_keyframe
from backseat_driver.bl.writer import write_json
from backseat_driver.models import SceneDescription, SceneKeyframe
from tests.fakes import FakeCaptioner, FakeSceneLoader, make_keyframe

pytest.importorskip("pytest_codspeed")

SCENE_COUNT = 500


@pytest.fixture
def keyframes() -> list[SceneKeyframe]:
    return [make_keyframe(n) for n in range(SCENE_COUNT)]


@pytest.fixture
def pipeline(keyframes: list[SceneKeyframe]) -> ScenePipeline:
    return ScenePipeline(loader=FakeSceneLoader(keyframes), captioner=FakeCaptioner())


@pytest.fixture
def descriptions(pipeline: ScenePipeline) -> list[SceneDescription]:
    return pipeline.run()


@pytest.mark.benchmark
def test_pipeline_run(pipeline: ScenePipeline) -> None:
    pipeline.run()


@pytest.mark.benchmark
def test_pipeline_run_capped(pipeline: ScenePipeline) -> None:
    pipeline.run(max_scenes=SCENE_COUNT // 10)


@pytest.mark.benchmark
def test_describe_keyframe(keyframes: list[SceneKeyframe]) -> None:
    captioner = FakeCaptioner()

    for keyframe in keyframes:
        describe_keyframe(keyframe, captioner)


@pytest.mark.benchmark
def test_write_json(descriptions: list[SceneDescription], tmp_path: Path) -> None:
    write_json(descriptions, str(tmp_path / "out.json"))
