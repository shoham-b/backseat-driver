"""Celery tasks sharing one pooled database store, run one after another on the worker process's loop.

Postgres connections (psycopg's async mode) are tied to the loop that opened them, so a loop started per task would
orphan the pool. SQLite's aiosqlite is more forgiving, so this checks the shared-store path end to end rather than
reproducing that failure; the Postgres behaviour needs a real server (the system tests).
"""

from pathlib import Path
from uuid import uuid4

from backseat_driver import tasks
from backseat_driver.models import CaptionTask, IngestTask, JobState
from backseat_driver.transport.caption_worker import CaptionWorker
from backseat_driver.transport.celery_job_queue import make_celery_app
from backseat_driver.transport.ingest_worker import IngestWorker
from backseat_driver.transport.job_store.sql_job_store import SqlJobStore
from backseat_driver.transport.worker_loop import worker_loop
from backseat_driver.write.job_store.storage import JobStorage
from tests.fakes import FakeCaptioner, FakeImageStore, FakeJobQueue, FakeSceneLoader, make_image_uri, make_keyframe


def test_tasks_run_one_after_another_over_the_same_pooled_store(tmp_path: Path) -> None:
    store = SqlJobStore(JobStorage(f"sqlite+aiosqlite:///{tmp_path / 'jobs.db'}"))
    worker_loop.run(store.ensure_schema())
    job_id, queue = uuid4(), FakeJobQueue()
    worker_loop.run(store.create_job(job_id, None, "tx"))
    keyframes = [make_keyframe(1), make_keyframe(2), make_keyframe(3)]
    registered = tasks.register_tasks(
        make_celery_app("memory://"),
        lambda: IngestWorker(FakeSceneLoader(keyframes), queue, store, FakeImageStore()),
        lambda: CaptionWorker(FakeCaptioner(), store, FakeImageStore()),
        lambda: store,
    )

    registered.ingest.apply(args=[IngestTask(job_id=job_id, transaction_id="tx").model_dump(mode="json")]).get()
    for keyframe in keyframes:
        payload = CaptionTask(
            job_id=job_id, transaction_id="tx", keyframe=keyframe, image_uri=make_image_uri(1)
        ).model_dump(mode="json")
        registered.caption.apply(args=[payload]).get()
    job = worker_loop.run(store.get_job(job_id))
    worker_loop.run(store.close())

    assert (job.state, job.completed_scenes) == (JobState.COMPLETED, 3)
