from datetime import UTC, datetime
from unittest import mock
from uuid import UUID, uuid4

import pytest

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


def _ingest(job_id: UUID, max_scenes: int | None = None) -> IngestTask:
    return IngestTask(job_id=job_id, transaction_id="tx", max_scenes=max_scenes)


def test_ingest_of_an_empty_dataset_completes_the_job_without_caption_tasks() -> None:
    job_id, queue, store = uuid4(), FakeJobQueue(), FakeJobStore()
    store.create_job(job_id, None, "tx")

    IngestWorker(FakeSceneLoader([]), queue, store, FakeImageStore()).handle(_ingest(job_id))

    assert queue.caption_tasks == []
    assert store.get_job(job_id).state == JobState.COMPLETED


def test_ingest_max_scenes_larger_than_the_dataset_takes_everything() -> None:
    job_id, queue, store = uuid4(), FakeJobQueue(), FakeJobStore()
    store.create_job(job_id, 99, "tx")

    IngestWorker(FakeSceneLoader([make_keyframe(1), make_keyframe(2)]), queue, store, FakeImageStore()).handle(
        _ingest(job_id, 99)
    )

    assert store.get_job(job_id).expected_scenes == 2
    assert len(queue.caption_tasks) == 2


def test_ingest_keeps_the_first_n_scenes_in_order() -> None:
    job_id, queue, store = uuid4(), FakeJobQueue(), FakeJobStore()
    store.create_job(job_id, 2, "tx")
    keyframes = [make_keyframe(n) for n in (5, 3, 9)]

    IngestWorker(FakeSceneLoader(keyframes), queue, store, FakeImageStore()).handle(_ingest(job_id, 2))

    assert [t.keyframe for t in queue.caption_tasks] == keyframes[:2]


def test_ingest_records_the_count_before_publishing_any_caption_task() -> None:
    job_id, store = uuid4(), FakeJobStore()
    store.create_job(job_id, None, "tx")
    seen_expected: list[int | None] = []

    class _ObservingQueue(FakeJobQueue):
        def enqueue_caption(self, task: CaptionTask) -> None:
            seen_expected.append(store.get_job(job_id).expected_scenes)

    queue = _ObservingQueue()

    IngestWorker(FakeSceneLoader([make_keyframe(1), make_keyframe(2)]), queue, store, FakeImageStore()).handle(
        _ingest(job_id)
    )

    assert seen_expected == [2, 2]


def test_ingest_redelivery_publishes_again_but_keeps_the_count_stable() -> None:
    job_id, queue, store = uuid4(), FakeJobQueue(), FakeJobStore()
    store.create_job(job_id, None, "tx")
    worker = IngestWorker(FakeSceneLoader([make_keyframe(1)]), queue, store, FakeImageStore())

    worker.handle(_ingest(job_id))
    worker.handle(_ingest(job_id))

    assert store.get_job(job_id).expected_scenes == 1
    assert len(queue.caption_tasks) == 2  # duplicates are absorbed by the idempotent caption step


def test_ingest_propagates_a_failing_loader_without_touching_the_store() -> None:
    job_id, queue, store = uuid4(), FakeJobQueue(), FakeJobStore()
    store.create_job(job_id, None, "tx")
    loader = mock.Mock()
    loader.load_keyframes.side_effect = FileNotFoundError("dataset missing")

    with pytest.raises(FileNotFoundError):
        IngestWorker(loader, queue, store, FakeImageStore()).handle(_ingest(job_id))

    assert store.get_job(job_id).expected_scenes is None
    assert queue.caption_tasks == []


def test_ingest_stops_fanning_out_when_the_queue_fails_so_the_message_is_retried() -> None:
    job_id, store = uuid4(), FakeJobStore()
    store.create_job(job_id, None, "tx")
    queue = mock.Mock()
    queue.enqueue_caption.side_effect = [None, ConnectionError("broker down")]

    with pytest.raises(ConnectionError):
        IngestWorker(FakeSceneLoader([make_keyframe(n) for n in (1, 2, 3)]), queue, store, FakeImageStore()).handle(
            _ingest(job_id)
        )

    assert queue.enqueue_caption.call_count == 2


def test_caption_failure_records_nothing() -> None:
    job_id, store = uuid4(), FakeJobStore()
    store.create_job(job_id, None, "tx")
    captioner = mock.Mock(model_name="m")
    captioner.caption.side_effect = RuntimeError("model exploded")
    task = CaptionTask(job_id=job_id, transaction_id="tx", keyframe=make_keyframe(1), image_uri=make_image_uri(1))

    with pytest.raises(RuntimeError, match="model exploded"):
        CaptionWorker(captioner, store, FakeImageStore()).handle(task)

    assert store.list_descriptions(job_id) == []


def test_caption_store_failure_propagates_so_the_message_is_not_acked() -> None:
    store = mock.Mock()
    store.record_description.side_effect = ConnectionError("db down")
    task = CaptionTask(job_id=uuid4(), transaction_id="tx", keyframe=make_keyframe(1), image_uri=make_image_uri(1))

    with pytest.raises(ConnectionError):
        CaptionWorker(FakeCaptioner(), store, FakeImageStore()).handle(task)


def test_caption_records_the_keyframe_fields_and_model_name() -> None:
    job_id, store = uuid4(), FakeJobStore()
    store.create_job(job_id, None, "tx")
    keyframe = make_keyframe(7)
    before = datetime.now(UTC)

    CaptionWorker(FakeCaptioner("dusk"), store, FakeImageStore()).handle(
        CaptionTask(job_id=job_id, transaction_id="tx", keyframe=keyframe, image_uri=make_image_uri(7))
    )
    [description] = store.list_descriptions(job_id)

    assert (description.scene_token, description.scene_name, description.image_path) == (
        keyframe.scene_token,
        keyframe.scene_name,
        keyframe.image_path,
    )
    assert (description.description, description.model_name) == ("dusk", "fake-model")
    assert description.generated_at >= before


def test_job_progress_moves_pending_running_completed() -> None:
    job_id, queue, store = uuid4(), FakeJobQueue(), FakeJobStore()
    store.create_job(job_id, None, "tx")
    states = [store.get_job(job_id).state]

    IngestWorker(FakeSceneLoader([make_keyframe(1), make_keyframe(2)]), queue, store, FakeImageStore()).handle(
        _ingest(job_id)
    )
    states.append(store.get_job(job_id).state)
    captioner = CaptionWorker(FakeCaptioner(), store, FakeImageStore())
    captioner.handle(queue.caption_tasks[0])
    states.append(store.get_job(job_id).state)
    captioner.handle(queue.caption_tasks[1])
    states.append(store.get_job(job_id).state)

    assert states == [JobState.PENDING, JobState.RUNNING, JobState.RUNNING, JobState.COMPLETED]
