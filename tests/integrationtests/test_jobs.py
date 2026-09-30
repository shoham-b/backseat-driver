from http import HTTPStatus
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from tests.fakes import FakeCaptioner, FakeJobQueue, FakeJobStore, FakeSceneLoader, make_keyframe
from vlmscene.api.app import app
from vlmscene.api.dependencies import get_job_queue, get_job_store
from vlmscene.bl.job_queue import CAPTION_QUEUE, INGEST_QUEUE, REQUEST_ID_HEADER
from vlmscene.bl.workers import CaptionWorker, IngestWorker
from vlmscene.models import IngestTask, JobState


def test_create_job_returns_accepted_and_enqueues_ingest(
    client: TestClient, job_queue: FakeJobQueue, job_store: FakeJobStore
) -> None:
    job_queue.published.clear()

    response = client.post("/jobs", json={"max_scenes": 3}, headers={REQUEST_ID_HEADER: "trace-7"})

    assert response.status_code == HTTPStatus.ACCEPTED
    body = response.json()
    assert body["state"] == JobState.PENDING
    [(queue_name, payload, headers)] = job_queue.published
    assert queue_name == INGEST_QUEUE
    assert IngestTask.model_validate_json(payload).max_scenes == 3
    assert headers[REQUEST_ID_HEADER] == "trace-7"
    assert job_store.get_job(IngestTask.model_validate_json(payload).job_id).max_scenes == 3


def test_create_job_without_body_processes_every_scene(client: TestClient) -> None:
    response = client.post("/jobs")

    assert response.status_code == HTTPStatus.ACCEPTED
    assert response.json()["max_scenes"] is None


def test_create_job_rejects_non_positive_max_scenes(client: TestClient) -> None:
    response = client.post("/jobs", json={"max_scenes": 0})

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


def test_get_unknown_job_is_not_found(client: TestClient) -> None:
    response = client.get(f"/jobs/{uuid4()}")

    assert response.status_code == HTTPStatus.NOT_FOUND


def test_list_descriptions_of_unknown_job_is_not_found(client: TestClient) -> None:
    response = client.get(f"/jobs/{uuid4()}/descriptions")

    assert response.status_code == HTTPStatus.NOT_FOUND


def test_job_runs_to_completion_through_both_workers(monkeypatch: pytest.MonkeyPatch) -> None:
    queue, store = FakeJobQueue(), FakeJobStore()
    monkeypatch.setitem(app.dependency_overrides, get_job_queue, lambda: queue)
    monkeypatch.setitem(app.dependency_overrides, get_job_store, lambda: store)
    client = TestClient(app)
    ingest = IngestWorker(FakeSceneLoader([make_keyframe(1), make_keyframe(2)]), queue, store)
    caption = CaptionWorker(FakeCaptioner(), store)

    job_id = client.post("/jobs").json()["job_id"]
    queue.consume(INGEST_QUEUE, ingest.handle)
    queue.consume(CAPTION_QUEUE, caption.handle)
    job = client.get(f"/jobs/{job_id}").json()
    descriptions = client.get(f"/jobs/{job_id}/descriptions").json()

    assert job["state"] == JobState.COMPLETED
    assert (job["expected_scenes"], job["completed_scenes"]) == (2, 2)
    assert [d["scene_name"] for d in descriptions] == ["scene-0001", "scene-0002"]
