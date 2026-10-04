from http import HTTPStatus
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from backseat_driver.api.app import create_app
from backseat_driver.api.dependencies import get_job_queue, get_job_store
from backseat_driver.api.middleware import REQUEST_ID_HEADER
from backseat_driver.captioning.backend_captioner import BackendCaptioner
from backseat_driver.config import RunMode, VlmBackend
from backseat_driver.datasets.s3_dataset_store import S3DatasetStore
from backseat_driver.jobs.celery_job_queue import CeleryJobQueue
from backseat_driver.jobs.in_memory_job_store import InMemoryJobStore
from backseat_driver.jobs.in_process_job_queue import InProcessJobQueue
from backseat_driver.jobs.sql_job_store import SqlJobStore
from backseat_driver.models import JobState
from tests.fakes import FakeJobQueue, FakeJobStore, make_settings
from tests.integrationtests.conftest import ClientFactory


@pytest.fixture
def isolated(client_with: ClientFactory) -> tuple[TestClient, FakeJobQueue, FakeJobStore]:
    queue, store = FakeJobQueue(), FakeJobStore()
    return client_with({get_job_queue: lambda: queue, get_job_store: lambda: store}), queue, store


@pytest.mark.parametrize("body", [{"max_scenes": -1}, {"max_scenes": "many"}, {"max_scenes": 1.5}, {"max_scenes": []}])
def test_create_job_rejects_an_invalid_scene_limit(
    isolated: tuple[TestClient, FakeJobQueue, FakeJobStore], body: dict
) -> None:
    client, queue, store = isolated

    response = client.post("/jobs", json=body)

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert queue.ingest_tasks == []
    assert store._jobs == {}


def test_create_job_accepts_an_explicit_null_limit(isolated: tuple[TestClient, FakeJobQueue, FakeJobStore]) -> None:
    client, *_ = isolated

    response = client.post("/jobs", json={"max_scenes": None})

    assert response.status_code == HTTPStatus.ACCEPTED
    assert response.json()["max_scenes"] is None


def test_create_job_ignores_unknown_body_fields(isolated: tuple[TestClient, FakeJobQueue, FakeJobStore]) -> None:
    client, *_ = isolated

    assert client.post("/jobs", json={"max_scenes": 2, "surprise": True}).status_code == HTTPStatus.ACCEPTED


def test_create_job_response_describes_a_pending_job(isolated: tuple[TestClient, FakeJobQueue, FakeJobStore]) -> None:
    client, queue, _ = isolated

    body = client.post("/jobs", json={"max_scenes": 4}).json()

    assert body["state"] == JobState.PENDING
    assert (body["expected_scenes"], body["completed_scenes"], body["max_scenes"]) == (None, 0, 4)
    assert UUID(body["job_id"]) == queue.ingest_tasks[0].job_id


def test_each_job_gets_its_own_id(isolated: tuple[TestClient, FakeJobQueue, FakeJobStore]) -> None:
    client, *_ = isolated

    ids = {client.post("/jobs").json()["job_id"] for _ in range(5)}

    assert len(ids) == 5


def test_the_request_id_is_the_transaction_id_end_to_end(
    isolated: tuple[TestClient, FakeJobQueue, FakeJobStore],
) -> None:
    client, queue, _ = isolated

    response = client.post("/jobs", headers={REQUEST_ID_HEADER: "trace-xyz"})

    assert response.headers[REQUEST_ID_HEADER] == "trace-xyz"
    assert response.json()["transaction_id"] == "trace-xyz"
    assert queue.ingest_tasks[0].transaction_id == "trace-xyz"


def test_a_generated_request_id_is_used_as_the_transaction_id(
    isolated: tuple[TestClient, FakeJobQueue, FakeJobStore],
) -> None:
    client, *_ = isolated

    response = client.post("/jobs")

    assert response.json()["transaction_id"] == response.headers[REQUEST_ID_HEADER]


def test_a_broker_outage_surfaces_as_a_server_error_not_a_silent_accept(client_with: ClientFactory) -> None:
    class _BrokenQueue(FakeJobQueue):
        def enqueue_ingest(self, task) -> None:
            raise ConnectionError("broker down")

    client = client_with(
        {get_job_queue: lambda: _BrokenQueue(), get_job_store: lambda: FakeJobStore()}, raise_server_exceptions=False
    )

    response = client.post("/jobs")

    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    assert response.json()["error"]["message"] == "internal server error"  # internals are not leaked


@pytest.mark.parametrize("path", ["/jobs/not-a-uuid", "/jobs/123", "/jobs/not-a-uuid/descriptions"])
def test_malformed_job_ids_are_validation_errors(client: TestClient, path: str) -> None:
    assert client.get(path).status_code == HTTPStatus.UNPROCESSABLE_ENTITY


def test_not_found_uses_the_standard_error_envelope(client: TestClient) -> None:
    unknown = uuid4()

    response = client.get(f"/jobs/{unknown}")

    assert response.json()["error"] == {
        "code": HTTPStatus.NOT_FOUND,
        "status": HTTPStatus.NOT_FOUND.phrase,
        "message": f"job {unknown} not found",
    }


def test_descriptions_of_a_job_with_no_results_yet_are_an_empty_list(
    isolated: tuple[TestClient, FakeJobQueue, FakeJobStore],
) -> None:
    client, *_ = isolated
    job_id = client.post("/jobs").json()["job_id"]

    response = client.get(f"/jobs/{job_id}/descriptions")

    assert response.status_code == HTTPStatus.OK
    assert response.json() == []


@pytest.mark.parametrize(("method", "path"), [("put", "/jobs"), ("delete", "/jobs"), ("post", f"/jobs/{uuid4()}")])
def test_unsupported_methods_are_rejected(client: TestClient, method: str, path: str) -> None:
    assert getattr(client, method)(path).status_code == HTTPStatus.METHOD_NOT_ALLOWED


def test_lifespan_wires_the_real_adapters_without_connecting() -> None:
    # No dependency overrides: this is what a deployed process builds. The default broker and database URLs
    # point at nothing, so startup only succeeds if none of the adapters connects while being constructed.
    settings = make_settings(vlm_backend=VlmBackend.HUGGINGFACE, mode=RunMode.DISTRIBUTED, dataset_bucket="nuscenes")
    service = create_app(settings)

    with TestClient(service) as client:
        state = client.app.state
        health = client.get("/health")

    assert isinstance(state.captioner, BackendCaptioner)
    assert isinstance(state.job_queue, CeleryJobQueue)
    assert isinstance(state.job_store, SqlJobStore)
    assert isinstance(state.image_store, S3DatasetStore)
    assert health.status_code == HTTPStatus.OK


def test_a_distributed_api_without_a_dataset_bucket_cannot_even_be_configured() -> None:
    with pytest.raises(ValueError, match="DATASET_BUCKET"):
        make_settings(vlm_backend=VlmBackend.HUGGINGFACE, mode=RunMode.DISTRIBUTED)


def test_lifespan_defaults_to_the_monolith_with_no_infrastructure() -> None:
    service = create_app(make_settings(vlm_backend=VlmBackend.HUGGINGFACE))

    with TestClient(service) as client:
        state = client.app.state
        job_id = client.post("/jobs").json()["job_id"]
        job = client.get(f"/jobs/{job_id}")

    assert isinstance(state.job_queue, InProcessJobQueue)
    assert isinstance(state.job_store, InMemoryJobStore)
    assert job.status_code == HTTPStatus.OK
