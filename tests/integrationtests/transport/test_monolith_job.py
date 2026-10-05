"""The monolith's job path: the in-process queue and store run the real workers, with no broker or database."""

from uuid import uuid4

from backseat_driver.models import IngestTask, JobState
from backseat_driver.stacks import build_job_backend
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


def test_a_job_whose_loader_fails_ends_failed_instead_of_hanging() -> None:
    class _MissingDataset(FakeSceneLoader):
        def load_keyframes(self) -> list:
            raise FileNotFoundError("dataset missing")

    queue, store = build_job_backend(
        make_settings(),
        FakeCaptioner(),
        FakeImageStore(),
        build_loader=lambda settings: _MissingDataset([]),
    )
    job_id = uuid4()
    store.create_job(job_id, None, "tx")

    queue.enqueue_ingest(IngestTask(job_id=job_id, transaction_id="tx"))
    wait_until(lambda: store.get_job(job_id).state is JobState.FAILED, "the job to fail")

    assert "dataset missing" in (store.get_job(job_id).error or "")
