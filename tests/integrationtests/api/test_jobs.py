from datetime import UTC, datetime
from http import HTTPStatus
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from backseat_driver.api.dependencies import get_job_queue, get_job_store
from backseat_driver.api.middleware import REQUEST_ID_HEADER
from backseat_driver.errors import IdempotencyKeyInUseError
from backseat_driver.models import DeadLetter, Job, JobState
from backseat_driver.transport.caption_worker import CaptionWorker
from backseat_driver.transport.ingest_worker import IngestWorker
from tests.fakes import FakeCaptioner, FakeImageStore, FakeJobQueue, FakeJobStore, FakeSceneLoader, make_keyframe
from tests.integrationtests.conftest import ClientFactory


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


def test_list_dead_letters_of_unknown_job_is_not_found(client: TestClient) -> None:
    response = client.get(f"/jobs/{uuid4()}/dead-letters")

    assert response.status_code == HTTPStatus.NOT_FOUND


def test_dead_letters_of_a_job_are_listed_with_their_payload(client_with: ClientFactory) -> None:
    store, job_id = FakeJobStore(), uuid4()
    store.create_job(job_id, None, "tx")
    store.record_dead_letter(
        job_id,
        DeadLetter(task="caption", payload={"job_id": str(job_id)}, error="OSError: gone", failed_at=datetime.now(UTC)),
    )
    client = client_with({get_job_store: lambda: store})

    letters = client.get(f"/jobs/{job_id}/dead-letters").json()

    assert [(letter["task"], letter["error"], letter["payload"]) for letter in letters] == [
        ("caption", "OSError: gone", {"job_id": str(job_id)})
    ]


def test_recent_dead_letters_span_jobs_newest_first_and_name_their_job(client_with: ClientFactory) -> None:
    store, first, second = FakeJobStore(), uuid4(), uuid4()
    for job_id in (first, second):
        store.create_job(job_id, None, "tx")
        store.record_dead_letter(
            job_id,
            DeadLetter(task="caption", payload={}, error=f"error {job_id}", failed_at=datetime.now(UTC)),
        )
    client = client_with({get_job_store: lambda: store})

    letters = client.get("/dead-letters").json()
    limited = client.get("/dead-letters", params={"limit": 1}).json()

    assert [letter["job_id"] for letter in letters] == [str(second), str(first)]
    assert [letter["job_id"] for letter in limited] == [str(second)]


def test_an_orphan_dead_letter_is_listed_with_a_null_job_id(client_with: ClientFactory) -> None:
    store = FakeJobStore()
    store.record_dead_letter(
        None, DeadLetter(task="caption", payload={"junk": 1}, error="ValidationError", failed_at=datetime.now(UTC))
    )
    client = client_with({get_job_store: lambda: store})

    [letter] = client.get("/dead-letters").json()

    assert (letter["job_id"], letter["payload"]) == (None, {"junk": 1})


def test_recent_dead_letters_reject_a_limit_out_of_range(client: TestClient) -> None:
    response = client.get("/dead-letters", params={"limit": 0})

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


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
