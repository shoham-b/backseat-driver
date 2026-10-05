from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from backseat_driver.write.job_store.storage import JobStorage


@pytest.fixture
def sqlite_storage() -> Iterator[JobStorage]:
    """A `JobStorage` over in-memory SQLite, so the real queries run without a Postgres server.

    SQLite accepts the `ON CONFLICT DO NOTHING` the Postgres insert emits, so idempotency is exercised for real.
    Postgres-only behaviour (pool options, dialect SQL) is covered separately in `test_job_storage.py`.
    """
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    job_storage = JobStorage("postgresql+psycopg://unused", engine_factory=lambda *_, **__: engine)
    job_storage.ensure_schema()
    yield job_storage
    engine.dispose()


@pytest.fixture(autouse=True)
def _hermetic_settings(no_ambient_settings: None) -> None:
    """Every test in this layer runs without the developer's `BACKSEAT_DRIVER_*` variables."""
