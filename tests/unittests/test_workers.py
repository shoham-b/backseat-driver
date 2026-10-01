from uuid import UUID, uuid4

import pytest

from backseat_driver.bl.errors import NotFoundError
from backseat_driver.bl.workers import CaptionWorker, IngestWorker
from backseat_driver.models import CaptionTask, IngestTask, JobState
from tests.fakes import FakeCaptioner, FakeJobQueue, FakeJobStore, FakeSceneLoader, make_keyframe


def _ingest_task(job_id: UUID, max_scenes: int | None = None) -> IngestTask:
    return IngestTask(job_id=job_id, transaction_id="tx-1", max_scenes=max_scenes)


def _caption_task(job_id: UUID, n: int = 1) -> CaptionTask:
    return CaptionTask(job_id=job_id, transaction_id="tx-1", keyframe=make_keyframe(n))


def test_ingest_fans_out_one_caption_task_per_scene() -> None:
    job_id, queue, store = uuid4(), FakeJobQueue(), FakeJobStore()
    store.create_job(job_id, None, "tx-1")
    worker = IngestWorker(FakeSceneLoader([make_keyframe(1), make_keyframe(2)]), queue, store)

    worker.handle(_ingest_task(job_id))

    assert [t.keyframe.scene_name for t in queue.caption_tasks] == ["scene-0001", "scene-0002"]
    assert {t.job_id for t in queue.caption_tasks} == {job_id}


def test_ingest_records_expected_scenes_and_honours_max_scenes() -> None:
    job_id, queue, store = uuid4(), FakeJobQueue(), FakeJobStore()
    store.create_job(job_id, 1, "tx-1")
    worker = IngestWorker(FakeSceneLoader([make_keyframe(1), make_keyframe(2)]), queue, store)

    worker.handle(_ingest_task(job_id, max_scenes=1))

    assert store.get_job(job_id).expected_scenes == 1
    assert len(queue.caption_tasks) == 1


def test_ingest_carries_the_transaction_id_onto_every_caption_task() -> None:
    job_id, queue, store = uuid4(), FakeJobQueue(), FakeJobStore()
    store.create_job(job_id, None, "tx-1")
    worker = IngestWorker(FakeSceneLoader([make_keyframe(1), make_keyframe(2)]), queue, store)

    worker.handle(_ingest_task(job_id))

    assert {t.transaction_id for t in queue.caption_tasks} == {"tx-1"}


def test_ingest_for_unknown_job_raises_before_enqueueing() -> None:
    queue = FakeJobQueue()
    worker = IngestWorker(FakeSceneLoader([make_keyframe(1)]), queue, FakeJobStore())

    with pytest.raises(NotFoundError):
        worker.handle(_ingest_task(uuid4()))

    assert queue.caption_tasks == []


def test_caption_worker_records_description() -> None:
    job_id, store = uuid4(), FakeJobStore()
    store.create_job(job_id, None, "tx-1")

    CaptionWorker(FakeCaptioner(), store).handle(_caption_task(job_id))

    [description] = store.list_descriptions(job_id)
    assert description.description == "a caption for /img/1.jpg"
    assert description.model_name == "fake-model"


def test_caption_redelivery_is_idempotent() -> None:
    job_id, store = uuid4(), FakeJobStore()
    store.create_job(job_id, None, "tx-1")
    store.set_expected_scenes(job_id, 1)
    worker = CaptionWorker(FakeCaptioner(), store)

    worker.handle(_caption_task(job_id))
    worker.handle(_caption_task(job_id))

    job = store.get_job(job_id)
    assert job.completed_scenes == 1
    assert job.state == JobState.COMPLETED
