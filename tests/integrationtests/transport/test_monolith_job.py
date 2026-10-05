"""The monolith's job path: the in-process queue and store run the real workers, with no broker or database."""

from uuid import UUID, uuid4

from backseat_driver.models import IngestTask, JobState, SceneKeyframe
from backseat_driver.stacks import build_job_backend
from backseat_driver.transport.job_store.job_store import JobStore
from tests.fakes import FakeCaptioner, FakeImageStore, FakeSceneLoader, make_keyframe, make_settings
from tests.waiting import wait_until


def test_a_job_runs_to_completion_without_a_broker() -> None:
    keyframes = [make_keyframe(1), make_keyframe(2)]
    queue, store = build_job_backend(
        make_settings(),
        FakeCaptioner(),
        FakeImageStore(),
        build_loader=lambda settings: FakeSceneLoader(keyframes),
    )
    job_id = uuid4()
    store.create_job(job_id, None, "tx")

    queue.enqueue_ingest(IngestTask(job_id=job_id, transaction_id="tx"))
    wait_until(lambda: store.get_job(job_id).state is JobState.COMPLETED, "the job to complete")

    assert [d.scene_name for d in store.list_descriptions(job_id)] == ["scene-0001", "scene-0002"]


class _MissingDataset(FakeSceneLoader):
    async def load_keyframes(self) -> list[SceneKeyframe]:
        raise OSError("dataset missing")


def _ingest_that_fails() -> tuple[JobStore, UUID]:
    """A monolith job whose ingest task has run and failed: the loader cannot find the dataset."""
    queue, store = build_job_backend(
        make_settings(),
        FakeCaptioner(),
        FakeImageStore(),
        build_loader=lambda settings: _MissingDataset([]),
    )
    job_id = uuid4()
    store.create_job(job_id, None, "tx")
    queue.enqueue_ingest(IngestTask(job_id=job_id, transaction_id="tx"))
    wait_until(
        lambda: store.get_job(job_id).state is JobState.FAILED and bool(store.list_dead_letters(job_id)),
        "the job to fail and its dead letter to be recorded",
    )
    return store, job_id


def test_a_job_whose_loader_fails_ends_failed_instead_of_hanging() -> None:
    store, job_id = _ingest_that_fails()

    assert "dataset missing" in (store.get_job(job_id).error or "")


def test_a_task_that_fails_is_kept_as_a_dead_letter() -> None:
    store, job_id = _ingest_that_fails()

    [letter] = store.list_dead_letters(job_id)

    assert (letter.task, letter.error, letter.payload["job_id"]) == ("ingest", "OSError: dataset missing", str(job_id))
