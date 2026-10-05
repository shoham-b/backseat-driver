"""`GET /jobs/{id}/dead-letters` and `GET /dead-letters`: the tasks that gave up, kept with their payload."""

from datetime import UTC, datetime
from http import HTTPStatus
from uuid import uuid4

from fastapi.testclient import TestClient

from backseat_driver.api.dependencies import get_job_store
from backseat_driver.models import DeadLetter
from tests.fakes import FakeJobStore
from tests.integrationtests.conftest import ClientFactory


def _dead_letter(error: str = "OSError: gone", payload: dict | None = None) -> DeadLetter:
    return DeadLetter(task="caption", payload=payload or {}, error=error, failed_at=datetime.now(UTC))


def test_list_dead_letters_of_unknown_job_is_not_found(client: TestClient) -> None:
    response = client.get(f"/jobs/{uuid4()}/dead-letters")

    assert response.status_code == HTTPStatus.NOT_FOUND


def test_dead_letters_of_a_job_are_listed_with_their_payload(client_with: ClientFactory) -> None:
    store, job_id = FakeJobStore(), uuid4()
    store.create_job(job_id, None, "tx")
    store.record_dead_letter(job_id, _dead_letter(payload={"job_id": str(job_id)}))
    client = client_with({get_job_store: lambda: store})

    letters = client.get(f"/jobs/{job_id}/dead-letters").json()

    assert [(letter["task"], letter["error"], letter["payload"]) for letter in letters] == [
        ("caption", "OSError: gone", {"job_id": str(job_id)})
    ]


def test_recent_dead_letters_span_jobs_newest_first_and_name_their_job(client_with: ClientFactory) -> None:
    store, first, second = FakeJobStore(), uuid4(), uuid4()
    for job_id in (first, second):
        store.create_job(job_id, None, "tx")
        store.record_dead_letter(job_id, _dead_letter(error=f"error {job_id}"))
    client = client_with({get_job_store: lambda: store})

    letters = client.get("/dead-letters").json()
    limited = client.get("/dead-letters", params={"limit": 1}).json()

    assert [letter["job_id"] for letter in letters] == [str(second), str(first)]
    assert [letter["job_id"] for letter in limited] == [str(second)]


def test_an_orphan_dead_letter_is_listed_with_a_null_job_id(client_with: ClientFactory) -> None:
    store = FakeJobStore()
    store.record_dead_letter(None, _dead_letter(error="ValidationError", payload={"junk": 1}))
    client = client_with({get_job_store: lambda: store})

    [letter] = client.get("/dead-letters").json()

    assert (letter["job_id"], letter["payload"]) == (None, {"junk": 1})


def test_recent_dead_letters_reject_a_limit_out_of_range(client: TestClient) -> None:
    response = client.get("/dead-letters", params={"limit": 0})

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
