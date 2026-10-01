"""CodSpeed benchmarks for the pure-Python parts of the pipeline.

Skipped when pytest-codspeed isn't installed (it's only installed in the CodSpeed workflow),
so the regular test run is unaffected. The model is faked: we measure our own overhead, not inference.
"""

from pathlib import Path

import pytest

from backseat_driver.bl.pipeline import ScenePipeline
from backseat_driver.bl.writer import write_json
from tests.fakes import FakeCaptioner, FakeSceneLoader, make_keyframe

pytest.importorskip("pytest_codspeed")

SCENE_COUNT = 500


@pytest.fixture
def pipeline() -> ScenePipeline:
    keyframes = [make_keyframe(n) for n in range(SCENE_COUNT)]
    return ScenePipeline(loader=FakeSceneLoader(keyframes), captioner=FakeCaptioner())


@pytest.mark.benchmark
def test_pipeline_run(pipeline: ScenePipeline) -> None:
    pipeline.run()


@pytest.mark.benchmark
def test_write_json(pipeline: ScenePipeline, tmp_path: Path) -> None:
    descriptions = pipeline.run()

    write_json(descriptions, str(tmp_path / "out.json"))
