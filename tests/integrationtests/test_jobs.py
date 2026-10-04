from http import HTTPStatus
from uuid import uuid4

from fastapi.testclient import TestClient

from backseat_driver.api.dependencies import get_job_queue, get_job_store
from backseat_driver.api.middleware import REQUEST_ID_HEADER
from backseat_driver.jobs.workers import CaptionWorker, IngestWorker
from backseat_driver.models import JobState
from tests.fakes import FakeCaptioner, FakeImageStore, FakeJobQueue, FakeJobStore, FakeSceneLoader, make_keyframe
from tests.integrationtests.conftest import ClientFactory


def test_create_job_returns_accepted_and_enqueues_ingest(
    client: TestClient, job_queue: FakeJobQueue, job_store: FakeJobStore
) -> None:
    job_queue.ingest_tasks.clear()

    response = client.post("/jobs", json={"max_scenes": 3}, headers={REQUEST_ID_HEADER: "trace-7"})

    assert response.status_code == HTTPStatus.ACCEPTED
    body = response.json()
    assert body["state"] == JobState.PENDING
    assert body["transaction_id"] == "trace-7"
    [task] = job_queue.ingest_tasks
    assert (task.max_scenes, task.transaction_id) == (3, "trace-7")
    assert job_store.get_job(task.job_id).max_scenes == 3


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


def test_job_runs_to_completion_through_both_workers(client_with: ClientFactory) -> None:
    queue, store = FakeJobQueue(), FakeJobStore()
    client = client_with({get_job_queue: lambda: queue, get_job_store: lambda: store})
    ingest = IngestWorker(FakeSceneLoader([make_keyframe(1), make_keyframe(2)]), queue, store, FakeImageStore())
    caption = CaptionWorker(FakeCaptioner(), store, FakeImageStore())

    job_id = client.post("/jobs").json()["job_id"]
    for ingest_task in queue.ingest_tasks:
        ingest.handle(ingest_task)
    for caption_task in queue.caption_tasks:
        caption.handle(caption_task)
    job = client.get(f"/jobs/{job_id}").json()
    descriptions = client.get(f"/jobs/{job_id}/descriptions").json()

    assert job["state"] == JobState.COMPLETED
    assert (job["expected_scenes"], job["completed_scenes"]) == (2, 2)
    assert [d["scene_name"] for d in descriptions] == ["scene-0001", "scene-0002"]
