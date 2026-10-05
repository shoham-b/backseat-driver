"""Behaviour every `JobStore` must have, run against each implementation.

The API and both workers are written against the port, and their tests use `FakeJobStore`; running the same cases
over the in-memory store, the SQL store and that fake keeps the fake honest.
"""

import time
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from backseat_driver.errors import NotFoundError
from backseat_driver.models import JobState, SceneDescription
from backseat_driver.write.job_store.in_memory_job_store import InMemoryJobStore
from backseat_driver.write.job_store.job_store import JobStore
from backseat_driver.write.job_store.sql_job_store import SqlJobStore
from tests.fakes import FakeJobStore

# What each store raises when a second job claims an idempotency key. They differ today: the SQL store lets the
# database's unique constraint speak, the other two check first. The API never reaches this path (it looks the key up
# before creating), so the difference is pinned here rather than hidden.
DUPLICATE_KEY_ERRORS = {"in_memory": ValueError, "fake": ValueError, "sql": IntegrityError}


@pytest.fixture(params=["in_memory", "sql", "fake"])
def store_kind(request: pytest.FixtureRequest) -> str:
    return request.param


@pytest.fixture
def store(store_kind: str, request: pytest.FixtureRequest) -> JobStore:
    if store_kind == "sql":
        return SqlJobStore(request.getfixturevalue("sqlite_storage"))
    return InMemoryJobStore() if store_kind == "in_memory" else FakeJobStore()


def _description(n: int, text: str | None = None, camera_channel: str = "CAM_FRONT") -> SceneDescription:
    return SceneDescription(
        scene_token=f"token-{n}",
        scene_name=f"scene-{n:04d}",
        camera_channel=camera_channel,
        image_path=f"samples/{camera_channel}/{n}.jpg",
        description=text or f"description {n}",
        model_name="fake-model",
        generated_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _new_job(store: JobStore, expected_scenes: int | None = None, idempotency_key: str | None = None) -> UUID:
    job_id = uuid4()
    store.create_job(job_id, None, "tx", idempotency_key)
    if expected_scenes is not None:
        store.set_expected_scenes(job_id, expected_scenes)
    return job_id


def test_a_new_job_is_pending_and_keeps_what_it_was_created_with(store: JobStore) -> None:
    job_id = uuid4()

    store.create_job(job_id, 4, "tx-1")
    job = store.get_job(job_id)

    assert job.state is JobState.PENDING
    assert (job.job_id, job.transaction_id, job.max_scenes) == (job_id, "tx-1", 4)
    assert (job.expected_scenes, job.completed_scenes, job.error) == (None, 0, None)


def test_a_job_is_running_once_the_scene_count_is_known(store: JobStore) -> None:
    job_id = _new_job(store)

    store.set_expected_scenes(job_id, 2)

    assert store.get_job(job_id).state is JobState.RUNNING


def test_a_job_is_completed_when_every_expected_scene_is_recorded(store: JobStore) -> None:
    job_id = _new_job(store, expected_scenes=2)
    store.record_description(job_id, _description(1))

    store.record_description(job_id, _description(2))
    job = store.get_job(job_id)

    assert (job.state, job.completed_scenes) == (JobState.COMPLETED, 2)


def test_a_job_with_no_scenes_is_completed_as_soon_as_that_is_known(store: JobStore) -> None:
    job_id = _new_job(store)

    store.set_expected_scenes(job_id, 0)

    assert store.get_job(job_id).state is JobState.COMPLETED


def test_a_redelivered_description_is_ignored_not_counted_or_overwritten(store: JobStore) -> None:
    job_id = _new_job(store, expected_scenes=2)
    store.record_description(job_id, _description(1))

    store.record_description(job_id, _description(1, text="redelivery"))

    assert store.get_job(job_id).completed_scenes == 1
    assert [d.description for d in store.list_descriptions(job_id)] == ["description 1"]


def test_descriptions_come_back_complete_and_sorted_by_scene_name(store: JobStore) -> None:
    job_id = _new_job(store)
    labelled = _description(1).model_copy(update={"reference_description": "Parked truck"})
    store.record_description(job_id, _description(2))
    store.record_description(job_id, labelled)

    descriptions = store.list_descriptions(job_id)

    assert [d.scene_name for d in descriptions] == ["scene-0001", "scene-0002"]
    # SQLite hands timestamps back without their timezone, which the Postgres column keeps.
    assert descriptions[0].model_dump(exclude={"generated_at"}) == labelled.model_dump(exclude={"generated_at"})


def test_each_camera_of_a_scene_is_recorded_and_counted(store: JobStore) -> None:
    job_id = _new_job(store, expected_scenes=2)

    store.record_description(job_id, _description(1, camera_channel="CAM_FRONT"))
    store.record_description(job_id, _description(1, camera_channel="CAM_BACK"))
    job = store.get_job(job_id)

    assert (job.state, job.completed_scenes) == (JobState.COMPLETED, 2)


def test_a_redelivered_camera_of_a_scene_is_ignored_next_to_its_other_cameras(store: JobStore) -> None:
    job_id = _new_job(store, expected_scenes=3)
    store.record_description(job_id, _description(1, camera_channel="CAM_FRONT"))
    store.record_description(job_id, _description(1, camera_channel="CAM_BACK"))

    store.record_description(job_id, _description(1, text="redelivery", camera_channel="CAM_BACK"))

    assert store.get_job(job_id).completed_scenes == 2
    assert [d.description for d in store.list_descriptions(job_id)] == ["description 1", "description 1"]


def test_descriptions_are_sorted_by_scene_name_then_camera(store: JobStore) -> None:
    job_id = _new_job(store)
    for n, camera_channel in [(2, "CAM_FRONT"), (1, "CAM_FRONT"), (1, "CAM_BACK")]:
        store.record_description(job_id, _description(n, camera_channel=camera_channel))

    descriptions = store.list_descriptions(job_id)

    assert [(d.scene_name, d.camera_channel) for d in descriptions] == [
        ("scene-0001", "CAM_BACK"),
        ("scene-0001", "CAM_FRONT"),
        ("scene-0002", "CAM_FRONT"),
    ]


def test_a_job_without_descriptions_lists_none(store: JobStore) -> None:
    job_id = _new_job(store)

    assert store.list_descriptions(job_id) == []


def test_descriptions_of_one_job_do_not_count_for_another(store: JobStore) -> None:
    first, second = _new_job(store, expected_scenes=1), _new_job(store, expected_scenes=1)

    store.record_description(first, _description(1))

    assert store.get_job(first).state is JobState.COMPLETED
    assert (store.get_job(second).state, store.get_job(second).completed_scenes) == (JobState.RUNNING, 0)


def test_a_failed_job_keeps_its_progress(store: JobStore) -> None:
    job_id = _new_job(store, expected_scenes=2)
    store.record_description(job_id, _description(1))

    store.fail_job(job_id, "boom")
    job = store.get_job(job_id)

    assert (job.state, job.error, job.completed_scenes) == (JobState.FAILED, "boom", 1)


def test_a_failed_job_keeps_the_first_error(store: JobStore) -> None:
    job_id = _new_job(store)

    store.fail_job(job_id, "first")
    store.fail_job(job_id, "second")

    assert store.get_job(job_id).error == "first"


def test_a_job_is_found_by_its_idempotency_key(store: JobStore) -> None:
    job_id = _new_job(store, idempotency_key="key-1")

    found = store.find_job_by_idempotency_key("key-1")

    assert found is not None
    assert found.job_id == job_id


def test_an_unknown_idempotency_key_finds_nothing(store: JobStore) -> None:
    _new_job(store, idempotency_key="key-1")

    assert store.find_job_by_idempotency_key("other") is None


def test_a_second_job_cannot_claim_a_used_idempotency_key(store: JobStore, store_kind: str) -> None:
    _new_job(store, idempotency_key="key-1")

    with pytest.raises(DUPLICATE_KEY_ERRORS[store_kind]):
        _new_job(store, idempotency_key="key-1")


def test_jobs_without_a_key_never_collide(store: JobStore) -> None:
    _new_job(store)
    _new_job(store)

    assert len(store.list_jobs()) == 2


def test_jobs_are_listed_newest_first_with_their_progress(store: JobStore) -> None:
    first = _new_job(store)
    time.sleep(0.05)  # the Windows clock ticks every ~16 ms, so back-to-back jobs would tie on `created_at`
    second = _new_job(store, expected_scenes=1)

    jobs = store.list_jobs()

    assert [(job.job_id, job.state) for job in jobs] == [(second, JobState.RUNNING), (first, JobState.PENDING)]


def test_a_store_without_jobs_lists_none(store: JobStore) -> None:
    assert store.list_jobs() == []


@pytest.mark.parametrize(
    "operation",
    [
        lambda store, job_id: store.get_job(job_id),
        lambda store, job_id: store.set_expected_scenes(job_id, 3),
        lambda store, job_id: store.fail_job(job_id, "boom"),
        lambda store, job_id: store.list_descriptions(job_id),
        lambda store, job_id: store.record_description(job_id, _description(1)),
    ],
    ids=["get_job", "set_expected_scenes", "fail_job", "list_descriptions", "record_description"],
)
def test_an_unknown_job_is_not_found(
    store: JobStore, store_kind: str, request: pytest.FixtureRequest, operation: Callable[[JobStore, UUID], object]
) -> None:
    if store_kind == "sql" and "record_description" in request.node.callspec.id:
        pytest.skip("SQLite does not enforce the foreign key; Postgres rejects the row with an IntegrityError")
    unknown = uuid4()

    with pytest.raises(NotFoundError, match=str(unknown)):
        operation(store, unknown)


def test_the_store_reports_itself_healthy(store: JobStore) -> None:
    assert store.healthcheck() is True
