"""Postgres persistence: engine/session lifecycle and queries over the ORM tables.

Returns ORM rows and primitives, never domain models; mapping to the domain is the adapter's job.
Never connects until first used.
"""

import threading
from uuid import UUID

from loguru import logger
from sqlalchemy import create_engine, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from backseat_driver.jobs.orm import Base, JobRow, SceneDescriptionRow


class JobStorage:
    """`database_url` must name the psycopg 3 driver, e.g. `postgresql+psycopg://...`."""

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url
        self._engine: Engine | None = None
        self._sessions: sessionmaker[Session] | None = None
        self._lock = threading.Lock()

    def ensure_schema(self) -> None:
        """Create the tables if missing. Run once per deployment (`db init`), not per process."""
        Base.metadata.create_all(self._get_engine())

    def insert_job(self, job_id: UUID, max_scenes: int | None, transaction_id: str) -> None:
        with self._session() as session, session.begin():
            session.add(JobRow(job_id=job_id, max_scenes=max_scenes, transaction_id=transaction_id))

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

    def insert_description(self, job_id: UUID, values: dict) -> None:
        """Idempotent: a redelivered scene is ignored."""
        statement = (
            pg_insert(SceneDescriptionRow)
            .values(job_id=job_id, **values)
            .on_conflict_do_nothing(index_elements=["job_id", "scene_token"])
        )
        with self._session() as session, session.begin():
            session.execute(statement)

    def fetch_job(self, job_id: UUID) -> tuple[JobRow, int] | None:
        """The job row and its completed-scene count, or None when no such job exists."""
        completed = select(func.count()).where(SceneDescriptionRow.job_id == JobRow.job_id).scalar_subquery()
        with self._session() as session:
            row = session.execute(select(JobRow, completed).where(JobRow.job_id == job_id)).one_or_none()
        return None if row is None else (row[0], row[1])

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
        # ping and startup failing fast against an unreachable host.
        if self._engine is None:
            self._engine = create_engine(
                self._database_url,
                pool_size=4,
                max_overflow=0,
                pool_pre_ping=True,
                connect_args={"connect_timeout": 10},
            )
        return self._engine
