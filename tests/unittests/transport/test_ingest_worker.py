from uuid import UUID, uuid4

import pytest

from backseat_driver.models import IngestTask, SceneKeyframe
from backseat_driver.transport.ingest_worker import IngestWorker
from tests.fakes import FakeImageStore, FakeJobQueue, FakeJobStore, FakeSceneLoader, make_keyframe


def _ingest_task(job_id: UUID, max_scenes: int | None = None) -> IngestTask:
    return IngestTask(job_id=job_id, transaction_id="tx-1", max_scenes=max_scenes)


def _new_job(store: FakeJobStore, max_scenes: int | None = None) -> UUID:
    job_id = uuid4()
    store.create_job(job_id, max_scenes, "tx-1")
    return job_id


def _worker(keyframes: list[SceneKeyframe], queue: FakeJobQueue, store: FakeJobStore) -> IngestWorker:
    return IngestWorker(FakeSceneLoader(keyframes), queue, store, FakeImageStore())


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
