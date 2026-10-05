"""SQL persistence (Postgres when distributed, SQLite for the monolith): engine/session lifecycle and queries
over the ORM tables, on SQLAlchemy's asyncio extension.

Returns ORM rows and primitives, never domain models; mapping to the domain is the adapter's job.
Never connects until first used.
"""

from collections.abc import Callable
from datetime import datetime
from typing import Any
from uuid import UUID

from loguru import logger
from sqlalchemy import ColumnElement, Connection, and_, event, func, inspect, select, update
from sqlalchemy.dialects.postgresql import Insert
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import make_url
from sqlalchemy.engine.interfaces import DBAPIConnection
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import ConnectionPoolEntry, NullPool
from sqlalchemy.sql.selectable import ScalarSelect

from backseat_driver.models import JobState
from backseat_driver.write.job_store.creation_clock import CreationClock
from backseat_driver.write.job_store.orm import Base, DeadLetterRow, JobRow, SceneDescriptionRow


def _completed_scenes() -> ScalarSelect[int]:
    """Per job row, how many descriptions have been recorded."""
    return select(func.count()).where(SceneDescriptionRow.job_id == JobRow.job_id).scalar_subquery()


def _in_state(state: JobState, completed: ScalarSelect[int]) -> ColumnElement[bool]:
    """The rows `derive_state` would put in `state`, so a listing can filter in the database.

    A job's state is never stored, hence this mirrors that function; a test pins the two together.
    """
    if state is JobState.FAILED:
        return JobRow.error.is_not(None)
    healthy = JobRow.error.is_(None)
    if state is JobState.PENDING:
        return and_(healthy, JobRow.expected_scenes.is_(None))
    if state is JobState.COMPLETED:
        return and_(healthy, JobRow.expected_scenes.is_not(None), completed >= JobRow.expected_scenes)
    return and_(healthy, JobRow.expected_scenes.is_not(None), completed < JobRow.expected_scenes)


def description_insert(job_id: UUID, values: dict) -> Insert:
    """The idempotent insert of one scene description (Postgres `ON CONFLICT DO NOTHING`)."""
    return (
        pg_insert(SceneDescriptionRow)
        .values(job_id=job_id, **values)
        .on_conflict_do_nothing(index_elements=["job_id", "scene_token", "camera_channel"])
    )


def _enforce_foreign_keys(dbapi_connection: DBAPIConnection, _record: ConnectionPoolEntry) -> None:
    """SQLite ignores foreign keys unless each connection asks for them; Postgres always enforces them."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


class JobStorage:
    """`database_url` names the psycopg 3 driver for Postgres (`postgresql+psycopg://...`) or the aiosqlite driver for a
    SQLite file (`sqlite+aiosqlite:///path`).

    A connection belongs to the event loop that opened it. The API has one loop for its whole life and keeps a pool; a
    caller that starts a loop per call (a Celery task) passes `pooled=False`, so every operation opens, and closes, a
    connection of its own and nothing outlives the loop it ran on.
    """

    def __init__(
        self,
        database_url: str,
        engine_factory: Callable[..., AsyncEngine] = create_async_engine,
        clock: Callable[[], datetime] | None = None,
        pooled: bool = True,
    ) -> None:
        self._database_url = database_url
        self._clock = clock or CreationClock()
        self._engine_factory = engine_factory
        self._pooled = pooled
        self._engine: AsyncEngine | None = None
        self._sessions: async_sessionmaker[AsyncSession] | None = None

    async def ensure_schema(self) -> None:
        """Create the tables if missing. Run once per deployment (`db init`), not per process.

        Raises RuntimeError when a table that already exists differs from what the code expects, in a column it lacks
        or in its primary key: `create_all` never alters a table, so an old database would otherwise fail on the first
        query that touches the new column, or on every description insert (whose `ON CONFLICT` target is the key).
        """
        async with self._get_engine().begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
            await connection.run_sync(_check_schema)

    async def close(self) -> None:
        """Release the pooled connections; the next operation opens new ones."""
        if self._engine is not None:
            await self._engine.dispose()

    async def insert_job(
        self, job_id: UUID, max_scenes: int | None, transaction_id: str, idempotency_key: str | None = None
    ) -> None:
        async with self._session() as session, session.begin():
            session.add(
                JobRow(
                    job_id=job_id,
                    max_scenes=max_scenes,
                    transaction_id=transaction_id,
                    idempotency_key=idempotency_key,
                    created_at=self._clock(),
                )
            )

    async def update_expected_scenes(self, job_id: UUID, expected_scenes: int) -> bool:
        """Return False when no such job exists."""
        statement = (
            update(JobRow)
            .where(JobRow.job_id == job_id)
            .values(expected_scenes=expected_scenes)
            .returning(JobRow.job_id)
        )
        async with self._session() as session, session.begin():
            return (await session.execute(statement)).first() is not None

    async def update_error(self, job_id: UUID, error: str) -> bool:
        """Keep the first error recorded. Return False when no such job exists."""
        statement = (
            update(JobRow)
            .where(JobRow.job_id == job_id)
            .values(error=func.coalesce(JobRow.error, error))
            .returning(JobRow.job_id)
        )
        async with self._session() as session, session.begin():
            return (await session.execute(statement)).first() is not None

    async def insert_dead_letter(self, job_id: UUID | None, values: dict) -> None:
        async with self._session() as session, session.begin():
            session.add(DeadLetterRow(job_id=job_id, **values))

    async def fetch_dead_letters(self, job_id: UUID) -> list[DeadLetterRow]:
        statement = select(DeadLetterRow).where(DeadLetterRow.job_id == job_id).order_by(DeadLetterRow.id)
        async with self._session() as session:
            return list((await session.scalars(statement)).all())

    async def fetch_recent_dead_letters(self, limit: int) -> list[DeadLetterRow]:
        statement = select(DeadLetterRow).order_by(DeadLetterRow.id.desc()).limit(limit)
        async with self._session() as session:
            return list((await session.scalars(statement)).all())

    async def insert_description(self, job_id: UUID, values: dict) -> None:
        """Idempotent: a redelivered scene and camera is ignored."""
        async with self._session() as session, session.begin():
            await session.execute(description_insert(job_id, values))

    async def fetch_job(self, job_id: UUID) -> tuple[JobRow, int] | None:
        """The job row and its completed-scene count, or None when no such job exists."""
        completed = _completed_scenes()
        async with self._session() as session:
            row = (await session.execute(select(JobRow, completed).where(JobRow.job_id == job_id))).one_or_none()
        return None if row is None else (row[0], row[1])

    async def fetch_job_by_key(self, idempotency_key: str) -> tuple[JobRow, int] | None:
        """Like `fetch_job`, for the job created under `idempotency_key`."""
        completed = _completed_scenes()
        statement = select(JobRow, completed).where(JobRow.idempotency_key == idempotency_key)
        async with self._session() as session:
            row = (await session.execute(statement)).one_or_none()
        return None if row is None else (row[0], row[1])

    async def fetch_jobs(self, state: JobState | None = None, limit: int | None = None) -> list[tuple[JobRow, int]]:
        """Job rows with their completed-scene counts, newest first; only those in `state`, at most `limit`."""
        completed = _completed_scenes()
        statement = select(JobRow, completed).order_by(JobRow.created_at.desc())
        if state is not None:
            statement = statement.where(_in_state(state, completed))
        if limit is not None:
            statement = statement.limit(limit)
        async with self._session() as session:
            rows = (await session.execute(statement)).all()
        return [(row[0], row[1]) for row in rows]

    async def fetch_descriptions(self, job_id: UUID) -> list[SceneDescriptionRow]:
        statement = (
            select(SceneDescriptionRow)
            .where(SceneDescriptionRow.job_id == job_id)
            .order_by(SceneDescriptionRow.scene_name, SceneDescriptionRow.camera_channel)
        )
        async with self._session() as session:
            return list((await session.scalars(statement)).all())

    async def ping(self) -> bool:
        try:
            async with self._get_engine().connect() as connection:
                await connection.exec_driver_sql("SELECT 1")
        except SQLAlchemyError as exc:
            logger.warning("database unreachable: {}", exc)
            return False
        return True

    def _session(self) -> AsyncSession:
        if self._sessions is None:
            self._sessions = async_sessionmaker(self._get_engine(), expire_on_commit=False)
        return self._sessions()

    def _get_engine(self) -> AsyncEngine:
        # create_async_engine is lazy: no connection is opened until first use. The connect timeout keeps ping and
        # startup failing fast against an unreachable host; for SQLite it is the wait on a locked file.
        if self._engine is None:
            is_sqlite = make_url(self._database_url).get_backend_name() == "sqlite"
            connect_args = {"timeout": 10} if is_sqlite else {"connect_timeout": 10}
            pool_options: dict[str, Any] = (
                {"pool_size": 4, "max_overflow": 0, "pool_pre_ping": True} if self._pooled else {"poolclass": NullPool}
            )
            engine = self._engine_factory(self._database_url, connect_args=connect_args, **pool_options)
            if engine.dialect.name == "sqlite":
                event.listen(engine.sync_engine, "connect", _enforce_foreign_keys)
            self._engine = engine
        return self._engine


def _check_schema(connection: Connection) -> None:
    existing = inspect(connection)
    for table in Base.metadata.sorted_tables:
        differences: list[str] = []
        missing = {column.name for column in table.columns} - {c["name"] for c in existing.get_columns(table.name)}
        if missing:
            differences.append(f"missing columns: {', '.join(sorted(missing))}")
        found_key = set(existing.get_pk_constraint(table.name)["constrained_columns"])
        expected_key = {column.name for column in table.primary_key.columns}
        if found_key != expected_key:
            differences.append(f"primary key {sorted(found_key)}, expected {sorted(expected_key)}")
        if differences:
            raise RuntimeError(
                f"table {table.name!r} in {connection.engine.url.render_as_string(hide_password=True)} predates the "
                f"current schema ({'; '.join(differences)}); there is no migration, so recreate the "
                "database (the monolith's output/jobs.db is only a job history and can be deleted)"
            )
