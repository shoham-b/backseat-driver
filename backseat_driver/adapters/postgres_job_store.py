"""Postgres adapter for the `JobStore` port, built on the SQLAlchemy ORM.

Never connects until first used.
"""

import threading
from datetime import datetime
from uuid import UUID

from loguru import logger
from sqlalchemy import DateTime, ForeignKey, Integer, String, create_engine, func, select, update
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from backseat_driver.bl.errors import NotFoundError
from backseat_driver.bl.job_store import JobStore, derive_state
from backseat_driver.models import Job, SceneDescription


class Base(DeclarativeBase):
    pass


class JobRow(Base):
    __tablename__ = "jobs"

    job_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    transaction_id: Mapped[str] = mapped_column(String)
    max_scenes: Mapped[int | None] = mapped_column(Integer)
    expected_scenes: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SceneDescriptionRow(Base):
    __tablename__ = "scene_descriptions"

    job_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("jobs.job_id"), primary_key=True)
    scene_token: Mapped[str] = mapped_column(String, primary_key=True)
    scene_name: Mapped[str] = mapped_column(String)
    camera_channel: Mapped[str] = mapped_column(String)
    image_path: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(String)
    model_name: Mapped[str] = mapped_column(String)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PostgresJobStore(JobStore):
    """`JobStore` backed by Postgres through a lazily created SQLAlchemy engine.

    `database_url` must name the psycopg 3 driver, e.g. `postgresql+psycopg://...`.
    """

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url
        self._engine: Engine | None = None
        self._sessions: sessionmaker[Session] | None = None
        self._lock = threading.Lock()

    def ensure_schema(self) -> None:
        """Create the tables if missing. Run once per deployment (`db init`), not per process."""
        Base.metadata.create_all(self._get_engine())

    def create_job(self, job_id: UUID, max_scenes: int | None, transaction_id: str) -> None:
        with self._session() as session, session.begin():
            session.add(JobRow(job_id=job_id, max_scenes=max_scenes, transaction_id=transaction_id))

    def set_expected_scenes(self, job_id: UUID, expected_scenes: int) -> None:
        statement = (
            update(JobRow)
            .where(JobRow.job_id == job_id)
            .values(expected_scenes=expected_scenes)
            .returning(JobRow.job_id)
        )
        with self._session() as session, session.begin():
            if session.execute(statement).first() is None:
                raise NotFoundError(f"job {job_id} not found")

    def record_description(self, job_id: UUID, description: SceneDescription) -> None:
        statement = (
            pg_insert(SceneDescriptionRow)
            .values(job_id=job_id, **description.model_dump())
            .on_conflict_do_nothing(index_elements=["job_id", "scene_token"])
        )
        with self._session() as session, session.begin():
            session.execute(statement)

    def get_job(self, job_id: UUID) -> Job:
        completed = select(func.count()).where(SceneDescriptionRow.job_id == JobRow.job_id).scalar_subquery()
        with self._session() as session:
            row = session.execute(select(JobRow, completed).where(JobRow.job_id == job_id)).one_or_none()
        if row is None:
            raise NotFoundError(f"job {job_id} not found")

        job, completed_scenes = row
        return Job(
            job_id=job_id,
            transaction_id=job.transaction_id,
            state=derive_state(job.expected_scenes, completed_scenes),
            max_scenes=job.max_scenes,
            expected_scenes=job.expected_scenes,
            completed_scenes=completed_scenes,
            created_at=job.created_at,
        )

    def list_descriptions(self, job_id: UUID) -> list[SceneDescription]:
        self.get_job(job_id)  # raises NotFoundError, so an unknown job isn't reported as "no descriptions"
        statement = (
            select(SceneDescriptionRow)
            .where(SceneDescriptionRow.job_id == job_id)
            .order_by(SceneDescriptionRow.scene_name)
        )
        with self._session() as session:
            rows = session.scalars(statement).all()
        return [
            SceneDescription(
                scene_token=row.scene_token,
                scene_name=row.scene_name,
                camera_channel=row.camera_channel,
                image_path=row.image_path,
                description=row.description,
                model_name=row.model_name,
                generated_at=row.generated_at,
            )
            for row in rows
        ]

    def healthcheck(self) -> bool:
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
        # healthcheck and startup failing fast against an unreachable host.
        if self._engine is None:
            self._engine = create_engine(
                self._database_url,
                pool_size=4,
                max_overflow=0,
                pool_pre_ping=True,
                connect_args={"connect_timeout": 10},
            )
        return self._engine
