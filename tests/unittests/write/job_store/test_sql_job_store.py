"""What is particular to the SQL store; the behaviour every store shares is in `test_job_store_contract.py`."""

from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from backseat_driver.write.job_store.sql_job_store import SqlJobStore
from backseat_driver.write.job_store.storage import JobStorage


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
