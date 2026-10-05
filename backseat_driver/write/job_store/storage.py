"""SQL persistence (Postgres when distributed, SQLite for the monolith): engine/session lifecycle and queries
over the ORM tables.

Returns ORM rows and primitives, never domain models; mapping to the domain is the adapter's job.
Never connects until first used.
"""

import threading
from collections.abc import Callable
from uuid import UUID

from loguru import logger
from sqlalchemy import create_engine, func, inspect, select, update
from sqlalchemy.dialects.postgresql import Insert
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from backseat_driver.write.job_store.orm import Base, JobRow, SceneDescriptionRow


def description_insert(job_id: UUID, values: dict) -> Insert:
    """The idempotent insert of one scene description (Postgres `ON CONFLICT DO NOTHING`)."""
    return (
        pg_insert(SceneDescriptionRow)
        .values(job_id=job_id, **values)
        .on_conflict_do_nothing(index_elements=["job_id", "scene_token"])
    )


class JobStorage:
    """`database_url` names the psycopg 3 driver for Postgres (`postgresql+psycopg://...`) or a SQLite file (`sqlite:///path`)."""

    def __init__(self, database_url: str, engine_factory: Callable[..., Engine] = create_engine) -> None:
        self._database_url = database_url
        self._engine_factory = engine_factory
        self._engine: Engine | None = None
        self._sessions: sessionmaker[Session] | None = None
        self._lock = threading.Lock()

    def ensure_schema(self) -> None:
        """Create the tables if missing. Run once per deployment (`db init`), not per process.

        Raises RuntimeError when a table that already exists lacks a column the code expects: `create_all` never alters
        a table, so an old database would otherwise fail on the first query that touches the new column.
        """
        engine = self._get_engine()
        Base.metadata.create_all(engine)
        existing = inspect(engine)
        for table in Base.metadata.sorted_tables:
            missing = {column.name for column in table.columns} - {c["name"] for c in existing.get_columns(table.name)}
            if missing:
                raise RuntimeError(
                    f"table {table.name!r} in {engine.url.render_as_string(hide_password=True)} predates the current "
                    f"schema (missing columns: {', '.join(sorted(missing))}); there is no migration, so recreate the "
                    "database (the monolith's output/jobs.db is only a job history and can be deleted)"
                )

    def insert_job(
        self, job_id: UUID, max_scenes: int | None, transaction_id: str, idempotency_key: str | None = None
    ) -> None:
        with self._session() as session, session.begin():
            session.add(
                JobRow(
                    job_id=job_id,
                    max_scenes=max_scenes,
                    transaction_id=transaction_id,
                    idempotency_key=idempotency_key,
                )
            )

    def update_expected_scenes(self, job_id: UUID, expected_scenes: int) -> bool:
        """Return False when no such job exists."""
        statement = (
            update(JobRow)
            .where(JobRow.job_id == job_id)
            .values(expected_scenes=expected_scenes)
            .returning(JobRow.job_id)
        )
        with self._session() as session, session.begin():
            return session.execute(statement).first() is not None

    def update_error(self, job_id: UUID, error: str) -> bool:
        """Keep the first error recorded. Return False when no such job exists."""
        statement = (
            update(JobRow)
            .where(JobRow.job_id == job_id)
            .values(error=func.coalesce(JobRow.error, error))
            .returning(JobRow.job_id)
        )
        with self._session() as session, session.begin():
            return session.execute(statement).first() is not None

    def insert_description(self, job_id: UUID, values: dict) -> None:
        """Idempotent: a redelivered scene is ignored."""
        with self._session() as session, session.begin():
            session.execute(description_insert(job_id, values))

    def fetch_job(self, job_id: UUID) -> tuple[JobRow, int] | None:
        """The job row and its completed-scene count, or None when no such job exists."""
        completed = select(func.count()).where(SceneDescriptionRow.job_id == JobRow.job_id).scalar_subquery()
        with self._session() as session:
            row = session.execute(select(JobRow, completed).where(JobRow.job_id == job_id)).one_or_none()
        return None if row is None else (row[0], row[1])

    def fetch_job_by_key(self, idempotency_key: str) -> tuple[JobRow, int] | None:
        """Like `fetch_job`, for the job created under `idempotency_key`."""
        completed = select(func.count()).where(SceneDescriptionRow.job_id == JobRow.job_id).scalar_subquery()
        statement = select(JobRow, completed).where(JobRow.idempotency_key == idempotency_key)
        with self._session() as session:
            row = session.execute(statement).one_or_none()
        return None if row is None else (row[0], row[1])

    def fetch_jobs(self) -> list[tuple[JobRow, int]]:
        """Every job row with its completed-scene count, newest first."""
        completed = select(func.count()).where(SceneDescriptionRow.job_id == JobRow.job_id).scalar_subquery()
        with self._session() as session:
            rows = session.execute(select(JobRow, completed).order_by(JobRow.created_at.desc())).all()
        return [(row[0], row[1]) for row in rows]

    def fetch_descriptions(self, job_id: UUID) -> list[SceneDescriptionRow]:
        statement = (
            select(SceneDescriptionRow)
            .where(SceneDescriptionRow.job_id == job_id)
            .order_by(SceneDescriptionRow.scene_name)
        )
        with self._session() as session:
            return list(session.scalars(statement).all())

    def ping(self) -> bool:
        try:
            with self._get_engine().connect() as conn:
                conn.exec_driver_sql("SELECT 1")
        except SQLAlchemyError as exc:
            logger.warning("postgres unreachable: {}", exc)
            return False
        return True

    def _session(self) -> Session:
        with self._lock:
            if self._sessions is None:
                self._sessions = sessionmaker(self._engine_unlocked(), expire_on_commit=False)
            return self._sessions()

    def _get_engine(self) -> Engine:
        with self._lock:
            return self._engine_unlocked()

    def _engine_unlocked(self) -> Engine:
        # create_engine is lazy: no connection is opened until first use. The connect timeout keeps
        # ping and startup failing fast against an unreachable host; for SQLite it is the wait on a locked file, and
        # the API threads and the in-process worker thread share one connection pool.
        if self._engine is None:
            is_sqlite = make_url(self._database_url).get_backend_name() == "sqlite"
            connect_args = {"timeout": 10, "check_same_thread": False} if is_sqlite else {"connect_timeout": 10}
            self._engine = self._engine_factory(
                self._database_url, pool_size=4, max_overflow=0, pool_pre_ping=True, connect_args=connect_args
            )
        return self._engine
