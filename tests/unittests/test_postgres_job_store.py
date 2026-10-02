from collections.abc import Callable
from datetime import UTC, datetime
from unittest import mock
from uuid import UUID, uuid4

import pytest

from backseat_driver.errors import NotFoundError
from backseat_driver.jobs import storage
from backseat_driver.jobs.postgres_job_store import PostgresJobStore
from backseat_driver.jobs.storage import JobStorage
from backseat_driver.models import JobState, SceneDescription


@pytest.fixture
def store(sqlite_storage: JobStorage) -> PostgresJobStore:
    job_store = PostgresJobStore("postgresql+psycopg://unused")
    job_store._storage = sqlite_storage
    return job_store


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
    with mock.patch.object(storage, "create_engine") as create_engine:
        PostgresJobStore("postgresql+psycopg://host/db")

    create_engine.assert_not_called()


def test_new_job_is_pending(store: PostgresJobStore) -> None:
    job_id = uuid4()

    store.create_job(job_id, max_scenes=4, transaction_id="tx-1")
    job = store.get_job(job_id)

    assert job.state == JobState.PENDING
    assert (job.job_id, job.transaction_id, job.max_scenes) == (job_id, "tx-1", 4)
    assert (job.expected_scenes, job.completed_scenes) == (None, 0)


def test_job_is_running_until_every_expected_scene_is_recorded(store: PostgresJobStore) -> None:
    job_id = uuid4()
    store.create_job(job_id, None, "tx")
    store.set_expected_scenes(job_id, 2)

    store.record_description(job_id, _description(1))
    running = store.get_job(job_id).state
    store.record_description(job_id, _description(2))
    completed = store.get_job(job_id).state

    assert (running, completed) == (JobState.RUNNING, JobState.COMPLETED)


def test_job_with_zero_expected_scenes_is_immediately_completed(store: PostgresJobStore) -> None:
    job_id = uuid4()
    store.create_job(job_id, None, "tx")

    store.set_expected_scenes(job_id, 0)

    assert store.get_job(job_id).state == JobState.COMPLETED


def test_recording_a_redelivered_description_does_not_inflate_progress(store: PostgresJobStore) -> None:
    job_id = uuid4()
    store.create_job(job_id, None, "tx")
    store.set_expected_scenes(job_id, 2)

    store.record_description(job_id, _description(1))
    store.record_description(job_id, _description(1, text="redelivery"))

    assert store.get_job(job_id).completed_scenes == 1
    assert [d.description for d in store.list_descriptions(job_id)] == ["description 1"]


def test_descriptions_round_trip_through_the_database_sorted_by_scene(store: PostgresJobStore) -> None:
    job_id = uuid4()
    store.create_job(job_id, None, "tx")
    for n in (2, 1):
        store.record_description(job_id, _description(n))

    descriptions = store.list_descriptions(job_id)

    assert [d.scene_name for d in descriptions] == ["scene-0001", "scene-0002"]
    assert descriptions[0].model_dump(exclude={"generated_at"}) == _description(1).model_dump(exclude={"generated_at"})


def test_a_job_with_no_descriptions_lists_none(store: PostgresJobStore) -> None:
    job_id = uuid4()
    store.create_job(job_id, None, "tx")

    assert store.list_descriptions(job_id) == []


@pytest.mark.parametrize(
    "operation",
    [
        lambda store, job_id: store.get_job(job_id),
        lambda store, job_id: store.set_expected_scenes(job_id, 3),
        lambda store, job_id: store.list_descriptions(job_id),
    ],
    ids=["get_job", "set_expected_scenes", "list_descriptions"],
)
def test_unknown_job_is_not_found(
    store: PostgresJobStore, operation: Callable[[PostgresJobStore, UUID], object]
) -> None:
    unknown = uuid4()

    with pytest.raises(NotFoundError, match=str(unknown)):
        operation(store, unknown)


def test_healthcheck_delegates_to_storage() -> None:
    job_store = PostgresJobStore("postgresql+psycopg://host/db")
    job_store._storage = mock.Mock(ping=mock.Mock(return_value=False))

    assert job_store.healthcheck() is False


def test_ensure_schema_is_safe_to_repeat(store: PostgresJobStore) -> None:
    job_id = uuid4()
    store.create_job(job_id, None, "tx")

    store.ensure_schema()

    assert store.get_job(job_id).transaction_id == "tx"
