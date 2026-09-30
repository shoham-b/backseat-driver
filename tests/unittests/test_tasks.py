from uuid import uuid4

import pytest
from pydantic import ValidationError

from tests.fakes import FakeCaptioner, FakeJobStore, make_keyframe
from vlmscene import tasks
from vlmscene.bl.workers import CaptionWorker
from vlmscene.models import CaptionTask


def test_caption_task_validates_the_payload_and_hands_it_to_the_worker(monkeypatch: pytest.MonkeyPatch) -> None:
    job_id, store = uuid4(), FakeJobStore()
    store.create_job(job_id, None, "tx-1")
    monkeypatch.setattr(tasks, "caption_worker", lambda: CaptionWorker(FakeCaptioner(), store))
    payload = CaptionTask(job_id=job_id, transaction_id="tx-1", keyframe=make_keyframe(1)).model_dump(mode="json")

    tasks.caption.apply(args=[payload]).get()

    assert store.get_job(job_id).completed_scenes == 1


def test_malformed_payload_fails_without_being_retried() -> None:
    result = tasks.caption.apply(args=[{"not": "a caption task"}])

    assert isinstance(result.result, ValidationError)
    assert result.traceback is not None
    assert result.state == "FAILURE"


def test_tasks_are_registered_under_the_names_the_api_publishes_to() -> None:
    assert {"vlmscene.ingest", "vlmscene.caption"} <= set(tasks.celery_app.tasks)
