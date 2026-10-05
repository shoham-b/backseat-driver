"""Benchmarks for the batch pipeline, the distributed workers and the JSON writer.

Everything runs against in-memory fakes, so the numbers track the orchestration and
model (de)serialization overhead around the VLM rather than the VLM itself.
"""

import asyncio
from pathlib import Path
from uuid import uuid4

import pytest
from pytest_codspeed import BenchmarkFixture

from backseat_driver.models import CaptionTask, IngestTask, SceneDescription
from backseat_driver.pipeline import ScenePipeline, describe_keyframes
from backseat_driver.transport.caption_worker import CaptionWorker
from backseat_driver.transport.ingest_worker import IngestWorker
from backseat_driver.write.json_writer import write_json
from tests.fakes import (
    FakeCaptioner,
    FakeJobQueue,
    FakeJobStore,
    FakeSceneLoader,
    PassthroughImageStore,
    make_image_uri,
    make_keyframe,
)

SCENE_COUNTS = [10, 500]


@pytest.mark.parametrize("scenes", SCENE_COUNTS)
def test_pipeline_run(benchmark: BenchmarkFixture, scenes: int) -> None:
    pipeline = ScenePipeline(
        FakeSceneLoader([make_keyframe(n) for n in range(scenes)]), FakeCaptioner(), PassthroughImageStore()
    )

    descriptions = benchmark(lambda: asyncio.run(pipeline.run()))

    assert len(descriptions) == scenes


@pytest.mark.parametrize("batch_size", [1, 8, 32])
def test_pipeline_run_by_batch_size(benchmark: BenchmarkFixture, batch_size: int) -> None:
    """The bookkeeping batching adds (an `ExitStack` of local copies per batch, one `caption_many` call)."""
    pipeline = ScenePipeline(
        FakeSceneLoader([make_keyframe(n) for n in range(500)]),
        FakeCaptioner(),
        PassthroughImageStore(),
        batch_size=batch_size,
    )

    descriptions = benchmark(lambda: asyncio.run(pipeline.run()))

    assert len(descriptions) == 500


@pytest.mark.parametrize("batch_size", [1, 8, 32])
def test_describe_keyframes(benchmark: BenchmarkFixture, batch_size: int) -> None:
    """Includes starting and closing an event loop, which `ScenePipeline.run` pays once per run."""
    keyframes = [make_keyframe(n) for n in range(batch_size)]
    paths = [keyframe.image_path for keyframe in keyframes]
    captioner = FakeCaptioner()

    descriptions = benchmark(lambda: asyncio.run(describe_keyframes(keyframes, captioner, paths)))

    assert len(descriptions) == batch_size


@pytest.mark.parametrize("scenes", SCENE_COUNTS)
def test_ingest_worker_fan_out(benchmark: BenchmarkFixture, scenes: int) -> None:
    loader = FakeSceneLoader([make_keyframe(n) for n in range(scenes)])
    queue = FakeJobQueue()
    store = FakeJobStore()
    job_id = uuid4()
    store.create_job(job_id, max_scenes=None, transaction_id="bench")
    worker = IngestWorker(loader, queue, store, PassthroughImageStore())
    task = IngestTask(job_id=job_id, transaction_id="bench")

    def run() -> None:
        queue.caption_tasks.clear()
        worker.handle(task)

    benchmark(run)

    assert len(queue.caption_tasks) == scenes


@pytest.mark.parametrize("scenes", SCENE_COUNTS)
def test_caption_worker_job_end_to_end(benchmark: BenchmarkFixture, scenes: int) -> None:
    """Caption every scene of a job and read back its state and results, as the API would."""
    keyframes = [make_keyframe(n) for n in range(scenes)]
    captioner = FakeCaptioner("a city street with cars and pedestrians")

    def run() -> list[SceneDescription]:
        store = FakeJobStore()
        job_id = uuid4()
        store.create_job(job_id, max_scenes=None, transaction_id="bench")
        store.set_expected_scenes(job_id, scenes)
        worker = CaptionWorker(captioner, store, PassthroughImageStore())
        for keyframe in keyframes:
            worker.handle(
                CaptionTask(job_id=job_id, transaction_id="bench", keyframe=keyframe, image_uri="fake://bench")
            )
        store.get_job(job_id)
        return store.list_descriptions(job_id)

    descriptions = benchmark(run)

    assert len(descriptions) == scenes


@pytest.mark.parametrize("scenes", SCENE_COUNTS)
def test_write_json(benchmark: BenchmarkFixture, tmp_path: Path, scenes: int) -> None:
    captioner = FakeCaptioner("a city street with cars and pedestrians")
    pipeline = ScenePipeline(
        FakeSceneLoader([make_keyframe(n) for n in range(scenes)]), captioner, PassthroughImageStore()
    )
    descriptions = asyncio.run(pipeline.run())
    output = tmp_path / "output" / "scene_descriptions.json"

    benchmark(write_json, descriptions, str(output))

    assert output.exists()


@pytest.mark.parametrize("scenes", SCENE_COUNTS)
def test_caption_task_round_trip(benchmark: BenchmarkFixture, scenes: int) -> None:
    """Serialize and re-validate queue messages, the work done per message on the broker boundary."""
    job_id = uuid4()
    payloads = [
        CaptionTask(
            job_id=job_id, transaction_id="bench", keyframe=make_keyframe(n), image_uri=make_image_uri(n)
        ).model_dump(mode="json")
        for n in range(scenes)
    ]

    def run() -> list[CaptionTask]:
        return [CaptionTask.model_validate(CaptionTask.model_validate(p).model_dump(mode="json")) for p in payloads]

    tasks = benchmark(run)

    assert len(tasks) == scenes
