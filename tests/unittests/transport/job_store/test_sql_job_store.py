"""What is particular to the SQL store; the behaviour every store shares is in `test_job_store_contract.py`."""

from typing import cast
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from backseat_driver.models import SceneDescription
from backseat_driver.transport.job_store.sql_job_store import SqlJobStore
from backseat_driver.write.job_store.storage import JobStorage
from tests.fakes import make_keyframe


@pytest.fixture
def store(sqlite_storage: JobStorage) -> SqlJobStore:
    return SqlJobStore(sqlite_storage)


class _DownStorage(JobStorage):
    def ping(self) -> bool:
        return False


def test_constructing_the_store_never_connects() -> None:
    engines_created: list[object] = []

    def engine_factory(*args: object, **kwargs: object) -> Engine:
        engines_created.append(args)
        return create_engine("sqlite://")

    job_storage = JobStorage("postgresql+psycopg://host/db", engine_factory=engine_factory)

    SqlJobStore(job_storage)

    assert engines_created == []


def test_healthcheck_delegates_to_storage() -> None:
    job_store = SqlJobStore(_DownStorage("postgresql+psycopg://host/db"))

    assert job_store.healthcheck() is False


def test_ensure_schema_is_safe_to_repeat(store: SqlJobStore) -> None:
    job_id = uuid4()
    store.create_job(job_id, None, "tx")

    store.ensure_schema()

    assert store.get_job(job_id).transaction_id == "tx"


def test_a_constraint_other_than_the_key_is_not_reported_as_a_taken_key(store: SqlJobStore) -> None:
    missing_transaction_id = cast(str, None)

    with pytest.raises(IntegrityError):
        store.create_job(uuid4(), None, missing_transaction_id, idempotency_key="key-1")


def test_a_constraint_other_than_the_job_is_not_reported_as_not_found(store: SqlJobStore) -> None:
    job_id = uuid4()
    store.create_job(job_id, None, "tx")
    description = SceneDescription(**make_keyframe(1).model_dump(), description="d", model_name="m")
    without_camera = description.model_copy(update={"camera_channel": None})  # copying skips validation

    with pytest.raises(IntegrityError):
        store.record_description(job_id, without_camera)
