from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from tests.fakes import FakeCaptioner, FakeJobQueue, FakeJobStore, FakeSceneLoader, make_keyframe
from vlmscene.bl.errors import NotFoundError
from vlmscene.bl.job_queue import CAPTION_QUEUE, REQUEST_ID_HEADER
from vlmscene.bl.workers import CaptionWorker, IngestWorker
from vlmscene.models import CaptionTask, IngestTask, JobState


def _ingest_body(job_id: UUID, max_scenes: int | None = None) -> bytes:
    return IngestTask(job_id=job_id, max_scenes=max_scenes).model_dump_json().encode()


def _caption_body(job_id: UUID, n: int = 1) -> bytes:
    return CaptionTask(job_id=job_id, keyframe=make_keyframe(n)).model_dump_json().encode()


def test_ingest_fans_out_one_caption_task_per_scene() -> None:
    job_id, queue, store = uuid4(), FakeJobQueue(), FakeJobStore()
    store.create_job(job_id, None)
    worker = IngestWorker(FakeSceneLoader([make_keyframe(1), make_keyframe(2)]), queue, store)

    worker.handle(_ingest_body(job_id), {})

    tasks = [CaptionTask.model_validate_json(body) for _, body, _ in queue.published]
    assert {queue_name for queue_name, _, _ in queue.published} == {CAPTION_QUEUE}
    assert [t.keyframe.scene_name for t in tasks] == ["scene-0001", "scene-0002"]
    assert {t.job_id for t in tasks} == {job_id}


def test_ingest_records_expected_scenes_and_honours_max_scenes() -> None:
    job_id, queue, store = uuid4(), FakeJobQueue(), FakeJobStore()
    store.create_job(job_id, 1)
    worker = IngestWorker(FakeSceneLoader([make_keyframe(1), make_keyframe(2)]), queue, store)

    worker.handle(_ingest_body(job_id, max_scenes=1), {})

    assert store.get_job(job_id).expected_scenes == 1
    assert len(queue.published) == 1


def test_ingest_forwards_request_id_header_to_caption_tasks() -> None:
    job_id, queue, store = uuid4(), FakeJobQueue(), FakeJobStore()
    store.create_job(job_id, None)
    worker = IngestWorker(FakeSceneLoader([make_keyframe(1)]), queue, store)

    worker.handle(_ingest_body(job_id), {REQUEST_ID_HEADER: "trace-1"})

    [(_, _, headers)] = queue.published
    assert headers[REQUEST_ID_HEADER] == "trace-1"


def test_ingest_for_unknown_job_raises_before_publishing() -> None:
    queue = FakeJobQueue()
    worker = IngestWorker(FakeSceneLoader([make_keyframe(1)]), queue, FakeJobStore())

    with pytest.raises(NotFoundError):
        worker.handle(_ingest_body(uuid4()), {})

    assert queue.published == []


def test_ingest_rejects_malformed_message() -> None:
    worker = IngestWorker(FakeSceneLoader([]), FakeJobQueue(), FakeJobStore())

    with pytest.raises(ValidationError):
        worker.handle(b"not json", {})


def test_caption_worker_records_description() -> None:
    job_id, store = uuid4(), FakeJobStore()
    store.create_job(job_id, None)

    CaptionWorker(FakeCaptioner(), store).handle(_caption_body(job_id), {})

    [description] = store.list_descriptions(job_id)
    assert description.description == "a caption for /img/1.jpg"
    assert description.model_name == "fake-model"


def test_caption_redelivery_is_idempotent() -> None:
    job_id, store = uuid4(), FakeJobStore()
    store.create_job(job_id, None)
    store.set_expected_scenes(job_id, 1)
    worker = CaptionWorker(FakeCaptioner(), store)

    worker.handle(_caption_body(job_id), {})
    worker.handle(_caption_body(job_id), {})

    job = store.get_job(job_id)
    assert job.completed_scenes == 1
    assert job.state == JobState.COMPLETED
