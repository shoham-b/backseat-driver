"""What is particular to the SQL store; the behaviour every store shares is in `test_job_store_contract.py`."""

from typing import cast
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from backseat_driver.models import JobState, SceneDescription
from backseat_driver.transport.job_store.sql_job_store import SqlJobStore
from backseat_driver.write.job_store.storage import JobStorage
from tests.fakes import make_keyframe


@pytest.fixture
def store(sqlite_storage: JobStorage) -> SqlJobStore:
    return SqlJobStore(sqlite_storage)


class _DownStorage(JobStorage):
    async def ping(self) -> bool:
        return False


def test_constructing_the_store_never_connects() -> None:
    engines_created: list[object] = []

    def engine_factory(*args: object, **kwargs: object) -> AsyncEngine:
        engines_created.append(args)
        return create_async_engine("sqlite+aiosqlite://")

    job_storage = JobStorage("postgresql+psycopg://host/db", engine_factory=engine_factory)

    SqlJobStore(job_storage)

    assert engines_created == []


async def test_healthcheck_delegates_to_storage() -> None:
    job_store = SqlJobStore(_DownStorage("postgresql+psycopg://host/db"))

    assert await job_store.healthcheck() is False


async def test_ensure_schema_is_safe_to_repeat(store: SqlJobStore) -> None:
    job_id = uuid4()
    await store.create_job(job_id, None, "tx")

    await store.ensure_schema()

    assert (await store.get_job(job_id)).transaction_id == "tx"


async def test_a_constraint_other_than_the_key_is_not_reported_as_a_taken_key(store: SqlJobStore) -> None:
    missing_transaction_id = cast(str, None)

    with pytest.raises(IntegrityError):
        await store.create_job(uuid4(), None, missing_transaction_id, idempotency_key="key-1")


async def test_a_constraint_other_than_the_job_is_not_reported_as_not_found(store: SqlJobStore) -> None:
    job_id = uuid4()
    await store.create_job(job_id, None, "tx")
    description = SceneDescription(**make_keyframe(1).model_dump(), description="d", model_name="m")
    without_camera = description.model_copy(update={"camera_channel": None})  # copying skips validation

    with pytest.raises(IntegrityError):
        await store.record_description(job_id, without_camera)


def _described(n: int) -> SceneDescription:
    return SceneDescription(**make_keyframe(n).model_dump(), description="a road", model_name="m")


async def test_the_database_state_filter_agrees_with_derive_state_for_every_combination(store: SqlJobStore) -> None:
    # expected: unknown or 0-2 scenes, completed: 0-2 descriptions, failed or not.
    for expected in (None, 0, 1, 2):
        for completed in range(3):
            for error in (None, "boom"):
                job_id = uuid4()
                await store.create_job(job_id, None, "tx")
                if expected is not None:
                    await store.set_expected_scenes(job_id, expected)
                for n in range(completed):
                    await store.record_description(job_id, _described(n))
                if error:
                    await store.fail_job(job_id, error)

    for state in JobState:
        assert {job.job_id for job in await store.list_jobs(state=state)} == {
            job.job_id for job in await store.list_jobs() if job.state is state
        }
