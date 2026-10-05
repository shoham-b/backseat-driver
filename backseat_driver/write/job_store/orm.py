"""SQLAlchemy ORM tables for the persistence layer. Query logic lives in `storage.py`."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Uuid, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class JobRow(Base):
    __tablename__ = "jobs"

    job_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    transaction_id: Mapped[str] = mapped_column(String)
    idempotency_key: Mapped[str | None] = mapped_column(String, unique=True)  # NULLs never collide
    max_scenes: Mapped[int | None] = mapped_column(Integer)
    expected_scenes: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(String)
    # The client-side default has microsecond resolution (CURRENT_TIMESTAMP has seconds on SQLite), so jobs created in
    # the same second still sort in creation order.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=lambda: datetime.now(UTC)
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
