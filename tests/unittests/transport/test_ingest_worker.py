from uuid import UUID, uuid4

import pytest

from backseat_driver.errors import NotFoundError
from backseat_driver.models import CaptionTask, IngestTask, JobState, SceneKeyframe
from backseat_driver.read.dataset.scene_loader import SceneLoader
from backseat_driver.transport.ingest_worker import IngestWorker
from tests.fakes import FakeImageStore, FakeJobQueue, FakeJobStore, FakeSceneLoader, make_image_uri, make_keyframe


def _ingest_task(job_id: UUID, max_scenes: int | None = None) -> IngestTask:
    return IngestTask(job_id=job_id, transaction_id="tx-1", max_scenes=max_scenes)


def _new_job(store: FakeJobStore, max_scenes: int | None = None) -> UUID:
    job_id = uuid4()
    store.create_job(job_id, max_scenes, "tx-1")
    return job_id


def _worker(keyframes: list[SceneKeyframe], queue: FakeJobQueue, store: FakeJobStore) -> IngestWorker:
    return IngestWorker(FakeSceneLoader(keyframes), queue, store, FakeImageStore())


class _MissingDataset(SceneLoader):
    async def load_keyframes(self) -> list[SceneKeyframe]:
        raise FileNotFoundError("dataset missing")


class _BrokerDiesOnSecondTask(FakeJobQueue):
    def enqueue_caption(self, task: CaptionTask) -> None:
        if self.caption_tasks:
            raise ConnectionError("broker down")
        super().enqueue_caption(task)


class _ObservingQueue(FakeJobQueue):
    """Notes what the store knew about the job each time a caption task was published."""

    def __init__(self, store: FakeJobStore, job_id: UUID) -> None:
        super().__init__()
        self.expected_when_published: list[int | None] = []
        self._store, self._job_id = store, job_id

    def enqueue_caption(self, task: CaptionTask) -> None:
        self.expected_when_published.append(self._store.get_job(self._job_id).expected_scenes)
        super().enqueue_caption(task)


def test_ingest_fans_out_one_caption_task_per_scene() -> None:
    queue, store = FakeJobQueue(), FakeJobStore()
    job_id = _new_job(store)

    _worker([make_keyframe(1), make_keyframe(2)], queue, store).handle(_ingest_task(job_id))

    assert [t.keyframe.scene_name for t in queue.caption_tasks] == ["scene-0001", "scene-0002"]
    assert {t.job_id for t in queue.caption_tasks} == {job_id}


def test_ingest_carries_the_transaction_id_onto_every_caption_task() -> None:
    queue, store = FakeJobQueue(), FakeJobStore()
    job_id = _new_job(store)

    _worker([make_keyframe(1), make_keyframe(2)], queue, store).handle(_ingest_task(job_id))

    assert {t.transaction_id for t in queue.caption_tasks} == {"tx-1"}


def test_ingest_points_each_caption_task_at_its_image_by_uri() -> None:
    queue, store = FakeJobQueue(), FakeJobStore()
    job_id = _new_job(store)

    _worker([make_keyframe(1), make_keyframe(2)], queue, store).handle(_ingest_task(job_id))

    assert [t.image_uri for t in queue.caption_tasks] == [make_image_uri(1), make_image_uri(2)]
    assert [t.keyframe.image_path for t in queue.caption_tasks] == ["/img/1.jpg", "/img/2.jpg"]


def test_ingest_records_how_many_scenes_to_expect() -> None:
    queue, store = FakeJobQueue(), FakeJobStore()
    job_id = _new_job(store)

    _worker([make_keyframe(1), make_keyframe(2)], queue, store).handle(_ingest_task(job_id))

    assert store.get_job(job_id).expected_scenes == 2


def test_ingest_of_an_empty_dataset_completes_the_job_without_caption_tasks() -> None:
    queue, store = FakeJobQueue(), FakeJobStore()
    job_id = _new_job(store)

    _worker([], queue, store).handle(_ingest_task(job_id))

    assert queue.caption_tasks == []
    assert store.get_job(job_id).state is JobState.COMPLETED


def test_ingest_keeps_only_the_first_max_scenes_in_order() -> None:
    queue, store = FakeJobQueue(), FakeJobStore()
    job_id = _new_job(store, max_scenes=2)
    keyframes = [make_keyframe(n) for n in (5, 3, 9)]

    _worker(keyframes, queue, store).handle(_ingest_task(job_id, max_scenes=2))

    assert [t.keyframe for t in queue.caption_tasks] == keyframes[:2]
    assert store.get_job(job_id).expected_scenes == 2


def test_ingest_with_a_max_scenes_beyond_the_dataset_takes_everything() -> None:
    queue, store = FakeJobQueue(), FakeJobStore()
    job_id = _new_job(store, max_scenes=99)

    _worker([make_keyframe(1), make_keyframe(2)], queue, store).handle(_ingest_task(job_id, max_scenes=99))

    assert store.get_job(job_id).expected_scenes == 2
    assert len(queue.caption_tasks) == 2


def test_ingest_records_the_count_before_publishing_any_caption_task() -> None:
    store = FakeJobStore()
    job_id = _new_job(store)
    queue = _ObservingQueue(store, job_id)

    _worker([make_keyframe(1), make_keyframe(2)], queue, store).handle(_ingest_task(job_id))

    assert queue.expected_when_published == [2, 2]


def test_ingest_redelivery_publishes_again_but_keeps_the_count_stable() -> None:
    queue, store = FakeJobQueue(), FakeJobStore()
    job_id = _new_job(store)
    worker = _worker([make_keyframe(1)], queue, store)

    worker.handle(_ingest_task(job_id))
    worker.handle(_ingest_task(job_id))

    assert store.get_job(job_id).expected_scenes == 1
    assert len(queue.caption_tasks) == 2  # duplicates are absorbed by the idempotent caption step


def test_ingest_for_an_unknown_job_raises_before_enqueueing() -> None:
    queue = FakeJobQueue()

    with pytest.raises(NotFoundError):
        _worker([make_keyframe(1)], queue, FakeJobStore()).handle(_ingest_task(uuid4()))

    assert queue.caption_tasks == []


def test_ingest_propagates_a_failing_loader_without_touching_the_store() -> None:
    queue, store = FakeJobQueue(), FakeJobStore()
    job_id = _new_job(store)

    with pytest.raises(FileNotFoundError):
        IngestWorker(_MissingDataset(), queue, store, FakeImageStore()).handle(_ingest_task(job_id))

    assert store.get_job(job_id).expected_scenes is None
    assert queue.caption_tasks == []


def test_ingest_stops_fanning_out_when_the_queue_fails_so_the_message_is_retried() -> None:
    queue, store = _BrokerDiesOnSecondTask(), FakeJobStore()
    job_id = _new_job(store)
    keyframes = [make_keyframe(n) for n in (1, 2, 3)]

    with pytest.raises(ConnectionError):
        _worker(keyframes, queue, store).handle(_ingest_task(job_id))

    assert [t.keyframe for t in queue.caption_tasks] == keyframes[:1]


def _both_cameras(n: int) -> list[SceneKeyframe]:
    front = make_keyframe(n)
    return [front, front.model_copy(update={"camera_channel": "CAM_BACK", "image_path": f"/img/{n}-back.jpg"})]


def test_ingest_expects_a_description_for_every_camera_of_every_scene() -> None:
    queue, store = FakeJobQueue(), FakeJobStore()
    job_id = _new_job(store)

    _worker(_both_cameras(1) + _both_cameras(2), queue, store).handle(_ingest_task(job_id))

    assert store.get_job(job_id).expected_scenes == 4
    assert len(queue.caption_tasks) == 4


def test_ingest_counts_max_scenes_in_scenes_not_cameras() -> None:
    queue, store = FakeJobQueue(), FakeJobStore()
    job_id = _new_job(store, max_scenes=1)
    keyframes = _both_cameras(1) + _both_cameras(2)

    _worker(keyframes, queue, store).handle(_ingest_task(job_id, max_scenes=1))

    assert [t.keyframe for t in queue.caption_tasks] == keyframes[:2]
    assert store.get_job(job_id).expected_scenes == 2


@pytest.mark.parametrize("max_scenes", [0, -1])
def test_ingest_rejects_a_max_scenes_below_one_instead_of_slicing(max_scenes: int) -> None:
    queue, store = FakeJobQueue(), FakeJobStore()
    job_id = _new_job(store, max_scenes=max_scenes)
    keyframes = [make_keyframe(n) for n in (1, 2, 3)]

    with pytest.raises(ValueError, match="max_scenes must be at least 1"):
        _worker(keyframes, queue, store).handle(_ingest_task(job_id, max_scenes=max_scenes))

    assert store.get_job(job_id).expected_scenes is None
    assert queue.caption_tasks == []
