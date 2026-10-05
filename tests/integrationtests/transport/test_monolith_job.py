"""The monolith's job path: the in-process queue and store run the real workers, with no broker or database."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID, uuid4

from backseat_driver.models import IngestTask, JobState, SceneKeyframe
from backseat_driver.stacks import build_job_backend
from backseat_driver.transport.job_queue import JobQueue
from backseat_driver.transport.job_store.job_store import JobStore
from tests.fakes import FakeCaptioner, FakeImageStore, FakeSceneLoader, make_keyframe, make_settings
from tests.waiting import wait_until_async


@asynccontextmanager
async def _monolith(loader: FakeSceneLoader) -> AsyncIterator[tuple[JobQueue, JobStore]]:
    queue, store = await build_job_backend(
        make_settings(), FakeCaptioner(), FakeImageStore(), build_loader=lambda settings: loader
    )
    try:
        yield queue, store
    finally:
        await queue.close()
        await store.close()


async def test_a_job_runs_to_completion_without_a_broker() -> None:
    async with _monolith(FakeSceneLoader([make_keyframe(1), make_keyframe(2)])) as (queue, store):
        job_id = uuid4()
        await store.create_job(job_id, None, "tx")

        await queue.enqueue_ingest(IngestTask(job_id=job_id, transaction_id="tx"))
        await wait_until_async(lambda: _is(store, job_id, JobState.COMPLETED), "the job to complete")

        assert [d.scene_name for d in await store.list_descriptions(job_id)] == ["scene-0001", "scene-0002"]


async def _is(store: JobStore, job_id: UUID, state: JobState) -> bool:
    return (await store.get_job(job_id)).state is state


class _MissingDataset(FakeSceneLoader):
    async def load_keyframes(self) -> list[SceneKeyframe]:
        raise OSError("dataset missing")


@asynccontextmanager
async def _ingest_that_fails() -> AsyncIterator[tuple[JobStore, UUID]]:
    """A monolith job whose ingest task has run and failed: the loader cannot find the dataset."""
    async with _monolith(_MissingDataset([])) as (queue, store):
        job_id = uuid4()
        await store.create_job(job_id, None, "tx")
        await queue.enqueue_ingest(IngestTask(job_id=job_id, transaction_id="tx"))

        async def failed_and_recorded() -> bool:
            return await _is(store, job_id, JobState.FAILED) and bool(await store.list_dead_letters(job_id))

        await wait_until_async(failed_and_recorded, "the job to fail and its dead letter to be recorded")
        yield store, job_id


async def test_a_job_whose_loader_fails_ends_failed_instead_of_hanging() -> None:
    async with _ingest_that_fails() as (store, job_id):
        assert "dataset missing" in ((await store.get_job(job_id)).error or "")


async def test_a_task_that_fails_is_kept_as_a_dead_letter() -> None:
    async with _ingest_that_fails() as (store, job_id):
        [letter] = await store.list_dead_letters(job_id)

        assert (letter.task, letter.error, letter.payload["job_id"]) == (
            "ingest",
            "OSError: dataset missing",
            str(job_id),
        )
