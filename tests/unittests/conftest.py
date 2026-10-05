from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from backseat_driver.write.job_store.storage import JobStorage


@pytest.fixture
async def sqlite_storage() -> AsyncIterator[JobStorage]:
    """A `JobStorage` over in-memory SQLite, so the real queries run without a Postgres server.

    SQLite accepts the `ON CONFLICT DO NOTHING` the Postgres insert emits, so idempotency is exercised for real.
    Postgres-only behaviour (pool options, dialect SQL) is covered separately in `test_job_storage.py`.
    """
    engine = create_async_engine("sqlite+aiosqlite://")
    job_storage = JobStorage("postgresql+psycopg://unused", engine_factory=lambda *_, **__: engine)
    await job_storage.ensure_schema()
    yield job_storage
    await engine.dispose()


@pytest.fixture(autouse=True)
def _hermetic_settings(no_ambient_settings: None) -> None:
    """Every test in this layer runs without the developer's settings."""
