"""SQLAlchemy ORM tables for the persistence layer. Query logic lives in `storage.py`."""

from datetime import UTC, datetime, timedelta
from threading import Lock
from uuid import UUID

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Uuid, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


_creation_lock = Lock()
_last_creation = datetime.min.replace(tzinfo=UTC)


def _creation_time() -> datetime:
    """Now, but strictly later than the previous call in this process.

    The wall clock ticks coarsely on some platforms (about 15 ms on Windows), so jobs created in a row would share a
    `created_at` and a newest-first listing could not tell them apart.
    """
    global _last_creation
    with _creation_lock:
        _last_creation = max(datetime.now(UTC), _last_creation + timedelta(microseconds=1))
        return _last_creation


class JobRow(Base):
    __tablename__ = "jobs"

    job_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    transaction_id: Mapped[str] = mapped_column(String)
    idempotency_key: Mapped[str | None] = mapped_column(String, unique=True)  # NULLs never collide
    max_scenes: Mapped[int | None] = mapped_column(Integer)
    expected_scenes: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(String)
    # Set by the client rather than CURRENT_TIMESTAMP (whole seconds on SQLite), so jobs created in a row still sort in
    # creation order.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=_creation_time
    )


class DeadLetterRow(Base):
    __tablename__ = "dead_letters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # NULL for an orphan: a task whose payload named no job.
    job_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("jobs.job_id"), index=True)
    task: Mapped[str] = mapped_column(String)
    payload: Mapped[dict] = mapped_column(JSON)
    error: Mapped[str] = mapped_column(String)
    failed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SceneDescriptionRow(Base):
    __tablename__ = "scene_descriptions"

    job_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("jobs.job_id"), primary_key=True)
    scene_token: Mapped[str] = mapped_column(String, primary_key=True)
    # Part of the key because a multi-camera job describes one scene once per camera.
    camera_channel: Mapped[str] = mapped_column(String, primary_key=True)
    scene_name: Mapped[str] = mapped_column(String)
    image_path: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(String)
    model_name: Mapped[str] = mapped_column(String)
    reference_description: Mapped[str | None] = mapped_column(String)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
