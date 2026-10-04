from pathlib import Path
from uuid import UUID, uuid4

import pytest

from backseat_driver.errors import NotFoundError
from backseat_driver.models import CaptionTask, IngestTask, JobState
from backseat_driver.transport.workers import CaptionWorker, IngestWorker
from tests.fakes import (
    FakeCaptioner,
    FakeImageStore,
    FakeJobQueue,
    FakeJobStore,
    FakeSceneLoader,
    make_image_uri,
    make_keyframe,
)


def _ingest_task(job_id: UUID, max_scenes: int | None = None) -> IngestTask:
    return IngestTask(job_id=job_id, transaction_id="tx-1", max_scenes=max_scenes)


def _caption_task(job_id: UUID, n: int = 1) -> CaptionTask:
    return CaptionTask(job_id=job_id, transaction_id="tx-1", keyframe=make_keyframe(n), image_uri=make_image_uri(n))


def test_ingest_fans_out_one_caption_task_per_scene() -> None:
    job_id, queue, store = uuid4(), FakeJobQueue(), FakeJobStore()
    store.create_job(job_id, None, "tx-1")
    worker = IngestWorker(FakeSceneLoader([make_keyframe(1), make_keyframe(2)]), queue, store, FakeImageStore())

    worker.handle(_ingest_task(job_id))

    assert [t.keyframe.scene_name for t in queue.caption_tasks] == ["scene-0001", "scene-0002"]
    assert {t.job_id for t in queue.caption_tasks} == {job_id}


def test_ingest_records_expected_scenes_and_honours_max_scenes() -> None:
    job_id, queue, store = uuid4(), FakeJobQueue(), FakeJobStore()
    store.create_job(job_id, 1, "tx-1")
    worker = IngestWorker(FakeSceneLoader([make_keyframe(1), make_keyframe(2)]), queue, store, FakeImageStore())

    worker.handle(_ingest_task(job_id, max_scenes=1))

    assert store.get_job(job_id).expected_scenes == 1
    assert len(queue.caption_tasks) == 1


def test_ingest_carries_the_transaction_id_onto_every_caption_task() -> None:
    job_id, queue, store = uuid4(), FakeJobQueue(), FakeJobStore()
    store.create_job(job_id, None, "tx-1")
    worker = IngestWorker(FakeSceneLoader([make_keyframe(1), make_keyframe(2)]), queue, store, FakeImageStore())

    worker.handle(_ingest_task(job_id))

    assert {t.transaction_id for t in queue.caption_tasks} == {"tx-1"}


def test_ingest_for_unknown_job_raises_before_enqueueing() -> None:
    queue = FakeJobQueue()
    worker = IngestWorker(FakeSceneLoader([make_keyframe(1)]), queue, FakeJobStore(), FakeImageStore())

    with pytest.raises(NotFoundError):
        worker.handle(_ingest_task(uuid4()))

    assert queue.caption_tasks == []


def test_caption_worker_records_description() -> None:
    job_id, store = uuid4(), FakeJobStore()
    store.create_job(job_id, None, "tx-1")

    CaptionWorker(FakeCaptioner(), store, FakeImageStore()).handle(_caption_task(job_id))

    [description] = store.list_descriptions(job_id)
    assert description.description == f"a caption for {Path('/fetched/1.jpg')}"
    assert description.model_name == "fake-model"


def test_caption_redelivery_is_idempotent() -> None:
    job_id, store = uuid4(), FakeJobStore()
    store.create_job(job_id, None, "tx-1")
    store.set_expected_scenes(job_id, 1)
    worker = CaptionWorker(FakeCaptioner(), store, FakeImageStore())

    worker.handle(_caption_task(job_id))
    worker.handle(_caption_task(job_id))

    job = store.get_job(job_id)
    assert job.completed_scenes == 1
    assert job.state == JobState.COMPLETED


def test_ingest_points_each_caption_task_at_its_image_by_uri() -> None:
    job_id, queue, store = uuid4(), FakeJobQueue(), FakeJobStore()
    store.create_job(job_id, None, "tx-1")
    worker = IngestWorker(FakeSceneLoader([make_keyframe(1), make_keyframe(2)]), queue, store, FakeImageStore())

    worker.handle(_ingest_task(job_id))

    assert [t.image_uri for t in queue.caption_tasks] == [make_image_uri(1), make_image_uri(2)]
    assert [t.keyframe.image_path for t in queue.caption_tasks] == ["/img/1.jpg", "/img/2.jpg"]


def test_caption_reads_the_local_copy_but_records_the_dataset_path() -> None:
    job_id, store, captioner, images = uuid4(), FakeJobStore(), FakeCaptioner(), FakeImageStore()
    store.create_job(job_id, None, "tx-1")

    CaptionWorker(captioner, store, images).handle(_caption_task(job_id))

    [description] = store.list_descriptions(job_id)
    assert captioner.seen_paths == [str(Path("/fetched/1.jpg"))]
    assert description.image_path == "/img/1.jpg"


def test_caption_releases_the_local_copy_even_when_captioning_fails() -> None:
    job_id, store, images = uuid4(), FakeJobStore(), FakeImageStore()
    store.create_job(job_id, None, "tx-1")

    class _FailingCaptioner(FakeCaptioner):
        def caption(self, image_path: str) -> str:
            raise RuntimeError("model exploded")

    with pytest.raises(RuntimeError):
        CaptionWorker(_FailingCaptioner(), store, images).handle(_caption_task(job_id))

    assert images.released == images.opened == [make_image_uri(1)]
