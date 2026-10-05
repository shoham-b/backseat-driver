"""Behaviour every `JobStore` must have, run against each implementation.

The API and both workers are written against the port, and their tests use `FakeJobStore`; running the same cases
over the in-memory store, the SQL store and that fake keeps the fake honest.
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from backseat_driver.models import JobState, SceneDescription
from backseat_driver.transport.job_store.in_memory_job_store import InMemoryJobStore
from backseat_driver.transport.job_store.job_store import JobStore
from backseat_driver.transport.job_store.sql_job_store import SqlJobStore
from tests.fakes import FakeJobStore


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
