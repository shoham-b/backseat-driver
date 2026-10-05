"""A job moving through the real ingest and caption workers, wired together over the in-memory queue and store."""

from uuid import uuid4

from backseat_driver.models import IngestTask, JobState
from backseat_driver.transport.caption_worker import CaptionWorker
from backseat_driver.transport.ingest_worker import IngestWorker
from tests.fakes import FakeCaptioner, FakeImageStore, FakeJobQueue, FakeJobStore, FakeSceneLoader, make_keyframe


def test_a_job_moves_from_pending_through_running_to_completed() -> None:
    job_id, queue, store = uuid4(), FakeJobQueue(), FakeJobStore()
    store.create_job(job_id, None, "tx")
    ingest = IngestWorker(FakeSceneLoader([make_keyframe(1), make_keyframe(2)]), queue, store, FakeImageStore())
    caption = CaptionWorker(FakeCaptioner(), store, FakeImageStore())
    states = [store.get_job(job_id).state]

    ingest.handle(IngestTask(job_id=job_id, transaction_id="tx"))
    states.append(store.get_job(job_id).state)
    caption.handle(queue.caption_tasks[0])
    states.append(store.get_job(job_id).state)
    caption.handle(queue.caption_tasks[1])
    states.append(store.get_job(job_id).state)

    assert states == [JobState.PENDING, JobState.RUNNING, JobState.RUNNING, JobState.COMPLETED]
