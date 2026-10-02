from collections.abc import Iterator
from unittest import mock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from backseat_driver.db import storage
from backseat_driver.db.storage import JobStorage


@pytest.fixture
def sqlite_storage() -> Iterator[JobStorage]:
    """A `JobStorage` over in-memory SQLite, so the real queries run without a Postgres server.

    SQLite accepts the `ON CONFLICT DO NOTHING` the Postgres insert emits, so idempotency is exercised for real.
    Postgres-only behaviour (pool options, dialect SQL) is covered separately in `test_job_storage.py`.
    """
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    with mock.patch.object(storage, "create_engine", return_value=engine):
        job_storage = JobStorage("postgresql+psycopg://unused")
        job_storage.ensure_schema()
        yield job_storage
    engine.dispose()
