"""Benchmarks for the batch pipeline, the distributed workers and the JSON writer.

Everything runs against in-memory fakes, so the numbers track the orchestration and
model (de)serialization overhead around the VLM rather than the VLM itself.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import pytest
from pytest_codspeed import BenchmarkFixture

from backseat_driver.models import CaptionTask, IngestTask, SceneDescription
from backseat_driver.pipeline import ScenePipeline
from backseat_driver.read.image_store import ImageStore
from backseat_driver.transport.caption_worker import CaptionWorker
from backseat_driver.transport.ingest_worker import IngestWorker
from backseat_driver.write.json_writer import write_json
from tests.fakes import (
    FakeCaptioner,
    FakeJobQueue,
    FakeJobStore,
    FakeSceneLoader,
    make_image_uri,
    make_keyframe,
)

SCENE_COUNTS = [10, 500]

_LOCAL_COPY = Path("/fetched/bench.jpg")


class _BenchImageStore(ImageStore):
    """Does the least an image store can, so the numbers measure the worker and not a test double's bookkeeping
    (FakeImageStore records every call and builds a path each time, which cost as much as the whole worker)."""

    def uri_for(self, key: str) -> str:
        return key

    @contextmanager
    def local_copy(self, uri: str) -> Iterator[Path]:
        yield _LOCAL_COPY


@pytest.mark.parametrize("scenes", SCENE_COUNTS)
def test_pipeline_run(benchmark: BenchmarkFixture, scenes: int) -> None:
    pipeline = ScenePipeline(FakeSceneLoader([make_keyframe(n) for n in range(scenes)]), FakeCaptioner())

    descriptions = benchmark(pipeline.run)

    assert len(descriptions) == scenes


@pytest.mark.parametrize("scenes", SCENE_COUNTS)
def test_ingest_worker_fan_out(benchmark: BenchmarkFixture, scenes: int) -> None:
    loader = FakeSceneLoader([make_keyframe(n) for n in range(scenes)])
    queue = FakeJobQueue()
    store = FakeJobStore()
    job_id = uuid4()
    store.create_job(job_id, max_scenes=None, transaction_id="bench")
    worker = IngestWorker(loader, queue, store, _BenchImageStore())
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
        worker = CaptionWorker(captioner, store, _BenchImageStore())
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
    descriptions = ScenePipeline(FakeSceneLoader([make_keyframe(n) for n in range(scenes)]), captioner).run()
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
