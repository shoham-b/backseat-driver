import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from backseat_driver.errors import NotFoundError
from backseat_driver.models import DeadLetter, JobState, SceneDescription
from backseat_driver.transport.job_store.sql_job_store import SqlJobStore
from backseat_driver.write.job_store.storage import JobStorage


@pytest.fixture
def store(sqlite_storage: JobStorage) -> SqlJobStore:
    return SqlJobStore(sqlite_storage)


def _description(n: int, text: str | None = None) -> SceneDescription:
    return SceneDescription(
        scene_token=f"token-{n}",
        scene_name=f"scene-{n:04d}",
        camera_channel="CAM_FRONT",
        image_path=f"/img/{n}.jpg",
        description=text or f"description {n}",
        model_name="fake-model",
        generated_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def test_constructing_the_store_never_connects() -> None:
    engines_created: list[object] = []

    def engine_factory(*args: object, **kwargs: object) -> Engine:
        engines_created.append(args)
        return create_engine("sqlite://")

    job_storage = JobStorage("postgresql+psycopg://host/db", engine_factory=engine_factory)

    SqlJobStore(job_storage)

    assert engines_created == []


def test_new_job_is_pending(store: SqlJobStore) -> None:
    job_id = uuid4()

    store.create_job(job_id, max_scenes=4, transaction_id="tx-1")
    job = store.get_job(job_id)

    assert job.state == JobState.PENDING
    assert (job.job_id, job.transaction_id, job.max_scenes) == (job_id, "tx-1", 4)
    assert (job.expected_scenes, job.completed_scenes) == (None, 0)


def test_job_is_running_until_every_expected_scene_is_recorded(store: SqlJobStore) -> None:
    job_id = uuid4()
    store.create_job(job_id, None, "tx")
    store.set_expected_scenes(job_id, 2)

    store.record_description(job_id, _description(1))
    running = store.get_job(job_id).state
    store.record_description(job_id, _description(2))
    completed = store.get_job(job_id).state

    assert (running, completed) == (JobState.RUNNING, JobState.COMPLETED)


def test_job_with_zero_expected_scenes_is_immediately_completed(store: SqlJobStore) -> None:
    job_id = uuid4()
    store.create_job(job_id, None, "tx")

    store.set_expected_scenes(job_id, 0)

    assert store.get_job(job_id).state == JobState.COMPLETED


def test_recording_a_redelivered_description_does_not_inflate_progress(store: SqlJobStore) -> None:
    job_id = uuid4()
    store.create_job(job_id, None, "tx")
    store.set_expected_scenes(job_id, 2)

    store.record_description(job_id, _description(1))
    store.record_description(job_id, _description(1, text="redelivery"))

    assert store.get_job(job_id).completed_scenes == 1
    assert [d.description for d in store.list_descriptions(job_id)] == ["description 1"]


def test_descriptions_round_trip_through_the_database_sorted_by_scene(store: SqlJobStore) -> None:
    job_id = uuid4()
    store.create_job(job_id, None, "tx")
    for n in (2, 1):
        store.record_description(job_id, _description(n))

    descriptions = store.list_descriptions(job_id)

    assert [d.scene_name for d in descriptions] == ["scene-0001", "scene-0002"]
    assert descriptions[0].model_dump(exclude={"generated_at"}) == _description(1).model_dump(exclude={"generated_at"})


def test_a_description_keeps_its_reference_label(store: SqlJobStore) -> None:
    job_id = uuid4()
    store.create_job(job_id, None, "tx")
    labelled = _description(1).model_copy(update={"reference_description": "Parked truck"})

    store.record_description(job_id, labelled)

    [stored] = store.list_descriptions(job_id)
    assert stored.reference_description == "Parked truck"


def test_a_failed_job_keeps_the_first_error_and_its_progress(store: SqlJobStore) -> None:
    job_id = uuid4()
    store.create_job(job_id, None, "tx")
    store.set_expected_scenes(job_id, 2)
    store.record_description(job_id, _description(1))

    store.fail_job(job_id, "first")
    store.fail_job(job_id, "second")

    job = store.get_job(job_id)
    assert (job.state, job.error, job.completed_scenes) == (JobState.FAILED, "first", 1)


def test_a_job_is_found_by_its_idempotency_key(store: SqlJobStore) -> None:
    job_id = uuid4()
    store.create_job(job_id, None, "tx", idempotency_key="key-1")

    found = store.find_job_by_idempotency_key("key-1")

    assert found is not None
    assert found.job_id == job_id
    assert store.find_job_by_idempotency_key("other") is None


def test_the_database_rejects_a_second_job_under_the_same_key(store: SqlJobStore) -> None:
    store.create_job(uuid4(), None, "tx", idempotency_key="key-1")

    with pytest.raises(IntegrityError):
        store.create_job(uuid4(), None, "tx", idempotency_key="key-1")


def test_jobs_without_a_key_never_collide(store: SqlJobStore) -> None:
    store.create_job(uuid4(), None, "tx")
    store.create_job(uuid4(), None, "tx")

    assert len(store.list_jobs()) == 2


def _dead_letter(task: Literal["ingest", "caption"] = "caption") -> DeadLetter:
    return DeadLetter(
        task=task,
        payload={"job_id": "j", "n": 1},
        error="ConnectionError: down",
        failed_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def test_dead_letters_round_trip_oldest_first_and_per_job(store: SqlJobStore) -> None:
    job_id, other = uuid4(), uuid4()
    store.create_job(job_id, None, "tx")
    store.create_job(other, None, "tx")

    store.record_dead_letter(job_id, _dead_letter("ingest"))
    store.record_dead_letter(job_id, _dead_letter("caption"))
    store.record_dead_letter(other, _dead_letter("caption"))

    letters = store.list_dead_letters(job_id)
    assert [letter.task for letter in letters] == ["ingest", "caption"]
    assert letters[0].model_dump(exclude={"failed_at"}) == _dead_letter("ingest").model_dump(exclude={"failed_at"})


def test_recent_dead_letters_span_jobs_newest_first_up_to_the_limit(store: SqlJobStore) -> None:
    first, second = uuid4(), uuid4()
    store.create_job(first, None, "tx")
    store.create_job(second, None, "tx")
    store.record_dead_letter(first, _dead_letter("ingest"))
    store.record_dead_letter(second, _dead_letter("caption"))
    store.record_dead_letter(first, _dead_letter("caption"))

    recent = store.list_recent_dead_letters(limit=2)

    assert [(letter.job_id, letter.task) for letter in recent] == [(first, "caption"), (second, "caption")]


def test_an_orphan_dead_letter_is_kept_without_a_job_and_listed_only_across_jobs(store: SqlJobStore) -> None:
    job_id = uuid4()
    store.create_job(job_id, None, "tx")

    store.record_dead_letter(None, _dead_letter("ingest"))

    [orphan] = store.list_recent_dead_letters(limit=10)
    assert (orphan.job_id, orphan.task) == (None, "ingest")
    assert store.list_dead_letters(job_id) == []


def test_no_dead_letters_lists_none(store: SqlJobStore) -> None:
    assert store.list_recent_dead_letters(limit=10) == []


def test_a_dead_letter_does_not_change_the_state_by_itself(store: SqlJobStore) -> None:
    job_id = uuid4()
    store.create_job(job_id, None, "tx")

    store.record_dead_letter(job_id, _dead_letter())

    assert store.get_job(job_id).state == JobState.PENDING


@pytest.mark.parametrize(
    "operation",
    [
        lambda store, job_id: store.record_dead_letter(job_id, _dead_letter()),
        lambda store, job_id: store.list_dead_letters(job_id),
    ],
    ids=["record_dead_letter", "list_dead_letters"],
)
def test_dead_letters_of_an_unknown_job_are_not_found(
    store: SqlJobStore, operation: Callable[[SqlJobStore, UUID], object]
) -> None:
    with pytest.raises(NotFoundError):
        operation(store, uuid4())


def test_a_job_with_no_descriptions_lists_none(store: SqlJobStore) -> None:
    job_id = uuid4()
    store.create_job(job_id, None, "tx")

    assert store.list_descriptions(job_id) == []


@pytest.mark.parametrize(
    "operation",
    [
        lambda store, job_id: store.get_job(job_id),
        lambda store, job_id: store.set_expected_scenes(job_id, 3),
        lambda store, job_id: store.fail_job(job_id, "boom"),
        lambda store, job_id: store.list_descriptions(job_id),
    ],
    ids=["get_job", "set_expected_scenes", "fail_job", "list_descriptions"],
)
def test_unknown_job_is_not_found(store: SqlJobStore, operation: Callable[[SqlJobStore, UUID], object]) -> None:
    unknown = uuid4()

    with pytest.raises(NotFoundError, match=str(unknown)):
        operation(store, unknown)


class _DownStorage(JobStorage):
    def ping(self) -> bool:
        return False


def test_healthcheck_delegates_to_storage() -> None:
    job_store = SqlJobStore(_DownStorage("postgresql+psycopg://host/db"))

    assert job_store.healthcheck() is False


def test_ensure_schema_is_safe_to_repeat(store: SqlJobStore) -> None:
    job_id = uuid4()
    store.create_job(job_id, None, "tx")

    store.ensure_schema()

    assert store.get_job(job_id).transaction_id == "tx"


def test_listing_jobs_returns_the_newest_first_with_their_progress(store: SqlJobStore) -> None:
    first, second = uuid4(), uuid4()
    store.create_job(first, None, "tx-1")
    time.sleep(0.05)  # the Windows clock ticks every ~16 ms, so back-to-back jobs would tie on `created_at`
    store.create_job(second, None, "tx-2")
    store.set_expected_scenes(second, 1)

    jobs = store.list_jobs()

    assert [(job.job_id, job.state) for job in jobs] == [(second, JobState.RUNNING), (first, JobState.PENDING)]


def test_listing_jobs_with_none_is_empty(store: SqlJobStore) -> None:
    assert store.list_jobs() == []
