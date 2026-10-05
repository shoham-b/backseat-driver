"""`POST /jobs` and `GET /jobs/{id}[/descriptions]`; the listing is in `test_jobs_listing.py`."""

from http import HTTPStatus
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from backseat_driver.api.dependencies import get_job_queue, get_job_store
from backseat_driver.api.middleware import REQUEST_ID_HEADER
from backseat_driver.errors import IdempotencyKeyInUseError
from backseat_driver.models import CaptionTask, IngestTask, Job, JobState
from backseat_driver.transport.caption_worker import CaptionWorker
from backseat_driver.transport.ingest_worker import IngestWorker
from tests.fakes import FakeCaptioner, FakeImageStore, FakeJobQueue, FakeJobStore, FakeSceneLoader, make_keyframe
from tests.integrationtests.conftest import ClientFactory


class _BrokenQueue(FakeJobQueue):
    def enqueue_ingest(self, task: IngestTask) -> None:
        raise ConnectionError("broker down")

    def enqueue_caption(self, task: CaptionTask) -> None:
        raise ConnectionError("broker down")


class _LookupMissesOnce(FakeJobStore):
    """The idempotency lookup misses the first time, as it does for a request that runs before the winner has
    created its job."""

    def __init__(self) -> None:
        super().__init__()
        self._missed = False

    def find_job_by_idempotency_key(self, idempotency_key: str) -> Job | None:
        if not self._missed:
            self._missed = True
            return None
        return super().find_job_by_idempotency_key(idempotency_key)


class _KeyTakenByNoJob(FakeJobStore):
    """Claims every key is taken yet finds no job under it, which a real store never does."""

    def create_job(
        self, job_id: UUID, max_scenes: int | None, transaction_id: str, idempotency_key: str | None = None
    ) -> None:
        raise IdempotencyKeyInUseError("order-1")


def test_create_job_returns_accepted_and_enqueues_ingest(
    client: TestClient, job_queue: FakeJobQueue, job_store: FakeJobStore
) -> None:
    response = client.post("/jobs", json={"max_scenes": 3}, headers={REQUEST_ID_HEADER: "trace-7"})

    assert response.status_code == HTTPStatus.ACCEPTED
    body = response.json()
    assert body["state"] == JobState.PENDING
    assert body["transaction_id"] == "trace-7"
    [task] = job_queue.ingest_tasks
    assert (task.max_scenes, task.transaction_id) == (3, "trace-7")
    assert job_store.get_job(task.job_id).max_scenes == 3


def test_create_job_response_describes_a_pending_job(client: TestClient, job_queue: FakeJobQueue) -> None:
    body = client.post("/jobs", json={"max_scenes": 4}).json()

    assert body["state"] == JobState.PENDING
    assert (body["expected_scenes"], body["completed_scenes"], body["max_scenes"]) == (None, 0, 4)
    assert UUID(body["job_id"]) == job_queue.ingest_tasks[0].job_id


@pytest.mark.parametrize("body", [None, {}, {"max_scenes": None}])
def test_create_job_without_a_limit_processes_every_scene(client: TestClient, body: dict | None) -> None:
    response = client.post("/jobs", json=body)

    assert response.status_code == HTTPStatus.ACCEPTED
    assert response.json()["max_scenes"] is None


def test_create_job_ignores_unknown_body_fields(client: TestClient) -> None:
    response = client.post("/jobs", json={"max_scenes": 2, "surprise": True})

    assert response.status_code == HTTPStatus.ACCEPTED


@pytest.mark.parametrize(
    "body", [{"max_scenes": 0}, {"max_scenes": -1}, {"max_scenes": "many"}, {"max_scenes": 1.5}, {"max_scenes": []}]
)
def test_create_job_rejects_an_invalid_scene_limit(
    client: TestClient, job_queue: FakeJobQueue, job_store: FakeJobStore, body: dict
) -> None:
    response = client.post("/jobs", json=body)

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert job_queue.ingest_tasks == []
    assert job_store.list_jobs() == []


def test_each_job_gets_its_own_id(client: TestClient) -> None:
    ids = {client.post("/jobs").json()["job_id"] for _ in range(5)}

    assert len(ids) == 5


def test_the_request_id_is_the_transaction_id_end_to_end(client: TestClient, job_queue: FakeJobQueue) -> None:
    response = client.post("/jobs", headers={REQUEST_ID_HEADER: "trace-xyz"})

    assert response.headers[REQUEST_ID_HEADER] == "trace-xyz"
    assert response.json()["transaction_id"] == "trace-xyz"
    assert job_queue.ingest_tasks[0].transaction_id == "trace-xyz"


def test_a_generated_request_id_is_used_as_the_transaction_id(client: TestClient) -> None:
    response = client.post("/jobs")

    assert response.json()["transaction_id"] == response.headers[REQUEST_ID_HEADER]


def test_a_malformed_request_id_is_replaced_not_stored(client: TestClient, job_queue: FakeJobQueue) -> None:
    response = client.post("/jobs", headers={REQUEST_ID_HEADER: "has spaces and ;"})

    assert response.headers[REQUEST_ID_HEADER] != "has spaces and ;"
    assert response.json()["transaction_id"] == response.headers[REQUEST_ID_HEADER]
    assert job_queue.ingest_tasks[0].transaction_id == response.headers[REQUEST_ID_HEADER]


def test_retrying_with_the_same_idempotency_key_returns_the_first_job(
    client: TestClient, job_queue: FakeJobQueue, job_store: FakeJobStore
) -> None:
    headers = {"Idempotency-Key": "order-1"}

    first = client.post("/jobs", headers=headers)
    second = client.post("/jobs", headers=headers)

    assert (first.status_code, second.status_code) == (HTTPStatus.ACCEPTED, HTTPStatus.OK)
    assert second.json()["job_id"] == first.json()["job_id"]
    assert len(job_queue.ingest_tasks) == 1
    assert len(job_store.list_jobs()) == 1


def test_different_idempotency_keys_start_different_jobs(client: TestClient, job_queue: FakeJobQueue) -> None:
    ids = {client.post("/jobs", headers={"Idempotency-Key": key}).json()["job_id"] for key in ("a", "b")}

    assert len(ids) == 2
    assert len(job_queue.ingest_tasks) == 2


@pytest.mark.parametrize("key", ["", "has space", "x" * 129])
def test_a_malformed_idempotency_key_is_rejected(client: TestClient, job_queue: FakeJobQueue, key: str) -> None:
    response = client.post("/jobs", headers={"Idempotency-Key": key})

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert job_queue.ingest_tasks == []


def test_a_retry_that_loses_the_race_for_its_key_gets_the_first_job_back(client_with: ClientFactory) -> None:
    queue, store = FakeJobQueue(), _LookupMissesOnce()
    first_job_id = uuid4()
    store.create_job(first_job_id, None, "tx-first", "order-1")
    client = client_with({get_job_queue: lambda: queue, get_job_store: lambda: store})

    response = client.post("/jobs", headers={"Idempotency-Key": "order-1"})

    assert response.status_code == HTTPStatus.OK
    assert UUID(response.json()["job_id"]) == first_job_id
    assert queue.ingest_tasks == []


def test_a_taken_key_without_a_job_is_a_conflict_not_a_server_error(client_with: ClientFactory) -> None:
    queue = FakeJobQueue()
    client = client_with({get_job_queue: lambda: queue, get_job_store: _KeyTakenByNoJob})

    response = client.post("/jobs", headers={"Idempotency-Key": "order-1"})

    assert response.status_code == HTTPStatus.CONFLICT
    assert queue.ingest_tasks == []


def test_a_broker_outage_surfaces_as_a_server_error_not_a_silent_accept(client_with: ClientFactory) -> None:
    client = client_with({get_job_queue: _BrokenQueue}, raise_server_exceptions=False)

    response = client.post("/jobs")

    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    assert response.json()["error"]["message"] == "internal server error"  # internals are not leaked


def test_a_job_that_could_not_be_enqueued_is_recorded_as_failed(client_with: ClientFactory) -> None:
    store = FakeJobStore()
    client = client_with({get_job_queue: _BrokenQueue, get_job_store: lambda: store}, raise_server_exceptions=False)

    client.post("/jobs")

    (job,) = store.list_jobs()
    assert job.state is JobState.FAILED
    assert job.error == "enqueue failed: ConnectionError: broker down"


def test_get_unknown_job_is_not_found(client: TestClient) -> None:
    response = client.get(f"/jobs/{uuid4()}")

    assert response.status_code == HTTPStatus.NOT_FOUND


def test_not_found_uses_the_standard_error_envelope(client: TestClient) -> None:
    unknown = uuid4()

    response = client.get(f"/jobs/{unknown}")

    assert response.json()["error"] == {
        "code": HTTPStatus.NOT_FOUND,
        "status": HTTPStatus.NOT_FOUND.phrase,
        "message": f"job {unknown} not found",
    }


def test_list_descriptions_of_unknown_job_is_not_found(client: TestClient) -> None:
    response = client.get(f"/jobs/{uuid4()}/descriptions")

    assert response.status_code == HTTPStatus.NOT_FOUND


@pytest.mark.parametrize("path", ["/jobs/not-a-uuid", "/jobs/123", "/jobs/not-a-uuid/descriptions"])
def test_malformed_job_ids_are_validation_errors(client: TestClient, path: str) -> None:
    assert client.get(path).status_code == HTTPStatus.UNPROCESSABLE_ENTITY


def test_descriptions_of_a_job_with_no_results_yet_are_an_empty_list(client: TestClient) -> None:
    job_id = client.post("/jobs").json()["job_id"]

    response = client.get(f"/jobs/{job_id}/descriptions")

    assert response.status_code == HTTPStatus.OK
    assert response.json() == []


@pytest.mark.parametrize(("method", "path"), [("put", "/jobs"), ("delete", "/jobs"), ("post", f"/jobs/{uuid4()}")])
def test_unsupported_methods_are_rejected(client: TestClient, method: str, path: str) -> None:
    assert getattr(client, method)(path).status_code == HTTPStatus.METHOD_NOT_ALLOWED


def test_job_runs_to_completion_through_both_workers(
    client: TestClient, job_queue: FakeJobQueue, job_store: FakeJobStore
) -> None:
    ingest = IngestWorker(FakeSceneLoader([make_keyframe(1), make_keyframe(2)]), job_queue, job_store, FakeImageStore())
    caption = CaptionWorker(FakeCaptioner(), job_store, FakeImageStore())

    job_id = client.post("/jobs").json()["job_id"]
    for ingest_task in job_queue.ingest_tasks:
        ingest.handle(ingest_task)
    for caption_task in job_queue.caption_tasks:
        caption.handle(caption_task)
    job = client.get(f"/jobs/{job_id}").json()
    descriptions = client.get(f"/jobs/{job_id}/descriptions").json()

    assert job["state"] == JobState.COMPLETED
    assert (job["expected_scenes"], job["completed_scenes"]) == (2, 2)
    assert [d["scene_name"] for d in descriptions] == ["scene-0001", "scene-0002"]
