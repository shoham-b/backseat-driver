"""`GET /jobs`: what the report UI uses to find the jobs worth showing."""

from http import HTTPStatus
from uuid import uuid4

from fastapi.testclient import TestClient

from backseat_driver.api.dependencies import get_job_queue, get_job_store
from backseat_driver.jobs.workers import CaptionWorker, IngestWorker
from backseat_driver.models import IngestTask, JobState
from tests.fakes import (
    FakeCaptioner,
    FakeJobQueue,
    FakeJobStore,
    FakeSceneLoader,
    make_keyframe,
)
from tests.integrationtests.conftest import ClientFactory


def _client(client_with: ClientFactory, store: FakeJobStore) -> TestClient:
    return client_with({get_job_queue: FakeJobQueue, get_job_store: lambda: store})


def test_jobs_are_listed_newest_first(client_with: ClientFactory) -> None:
    store, first, second = FakeJobStore(), uuid4(), uuid4()
    store.create_job(first, None, "tx-1")
    store.create_job(second, None, "tx-2")

    response = _client(client_with, store).get("/jobs")

    assert response.status_code == HTTPStatus.OK
    assert [job["job_id"] for job in response.json()] == [str(second), str(first)]


def test_an_empty_store_lists_no_jobs(client_with: ClientFactory) -> None:
    assert _client(client_with, FakeJobStore()).get("/jobs").json() == []


def test_jobs_can_be_filtered_by_state(client_with: ClientFactory) -> None:
    store, queue, pending, done = FakeJobStore(), FakeJobQueue(), uuid4(), uuid4()
    store.create_job(pending, None, "tx-1")
    store.create_job(done, None, "tx-2")
    IngestWorker(FakeSceneLoader([make_keyframe(1)]), queue, store).handle(IngestTask(job_id=done, transaction_id="tx"))
    CaptionWorker(FakeCaptioner(), store).handle(queue.caption_tasks[0])
    client = _client(client_with, store)

    completed = client.get("/jobs", params={"state": JobState.COMPLETED.value}).json()
    waiting = client.get("/jobs", params={"state": JobState.PENDING.value}).json()

    assert [job["job_id"] for job in completed] == [str(done)]
    assert [job["job_id"] for job in waiting] == [str(pending)]


def test_the_listing_is_capped_by_limit(client_with: ClientFactory) -> None:
    store = FakeJobStore()
    for _ in range(3):
        store.create_job(uuid4(), None, "tx")

    response = _client(client_with, store).get("/jobs", params={"limit": 2})

    assert len(response.json()) == 2


def test_a_limit_outside_the_allowed_range_is_rejected(client_with: ClientFactory) -> None:
    client = _client(client_with, FakeJobStore())

    assert client.get("/jobs", params={"limit": 0}).status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert client.get("/jobs", params={"limit": 501}).status_code == HTTPStatus.UNPROCESSABLE_ENTITY
