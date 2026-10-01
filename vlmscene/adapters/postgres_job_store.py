"""Postgres adapter for the `JobStore` port, using a lazily opened psycopg connection pool.

Imports psycopg lazily and never connects until first used.
"""

import threading
from typing import Any
from uuid import UUID

from loguru import logger

from vlmscene.bl.errors import NotFoundError
from vlmscene.bl.job_store import JobStore, derive_state
from vlmscene.models import Job, SceneDescription

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    job_id          uuid PRIMARY KEY,
    transaction_id  text NOT NULL,
    max_scenes      integer,
    expected_scenes integer,
    created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS scene_descriptions (
    job_id         uuid NOT NULL REFERENCES jobs (job_id),
    scene_token    text NOT NULL,
    scene_name     text NOT NULL,
    camera_channel text NOT NULL,
    image_path     text NOT NULL,
    description    text NOT NULL,
    model_name     text NOT NULL,
    generated_at   timestamptz NOT NULL,
    PRIMARY KEY (job_id, scene_token)
);
"""


class PostgresJobStore(JobStore):
    """`JobStore` backed by Postgres through a lazily opened psycopg connection pool."""

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url
        self._pool: Any | None = None
        self._lock = threading.Lock()

    def ensure_schema(self) -> None:
        """Create the tables if missing. Run once per deployment (`db init`), not per process."""
        with self._get_pool().connection() as conn:
            conn.execute(_SCHEMA)

    def create_job(self, job_id: UUID, max_scenes: int | None, transaction_id: str) -> None:
        with self._get_pool().connection() as conn:
            conn.execute(
                "INSERT INTO jobs (job_id, max_scenes, transaction_id) VALUES (%s, %s, %s)",
                (job_id, max_scenes, transaction_id),
            )

    def set_expected_scenes(self, job_id: UUID, expected_scenes: int) -> None:
        with self._get_pool().connection() as conn:
            cursor = conn.execute("UPDATE jobs SET expected_scenes = %s WHERE job_id = %s", (expected_scenes, job_id))
            if cursor.rowcount == 0:
                raise NotFoundError(f"job {job_id} not found")

    def record_description(self, job_id: UUID, description: SceneDescription) -> None:
        with self._get_pool().connection() as conn:
            conn.execute(
                """
                INSERT INTO scene_descriptions
                    (job_id, scene_token, scene_name, camera_channel, image_path, description, model_name, generated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (job_id, scene_token) DO NOTHING
                """,
                (
                    job_id,
                    description.scene_token,
                    description.scene_name,
                    description.camera_channel,
                    description.image_path,
                    description.description,
                    description.model_name,
                    description.generated_at,
                ),
            )

    def get_job(self, job_id: UUID) -> Job:
        with self._get_pool().connection() as conn:
            row = conn.execute(
                """
                SELECT j.transaction_id, j.max_scenes, j.expected_scenes, j.created_at,
                       (SELECT count(*) FROM scene_descriptions d WHERE d.job_id = j.job_id)
                FROM jobs j WHERE j.job_id = %s
                """,
                (job_id,),
            ).fetchone()
        if row is None:
            raise NotFoundError(f"job {job_id} not found")

        transaction_id, max_scenes, expected_scenes, created_at, completed_scenes = row
        return Job(
            job_id=job_id,
            transaction_id=transaction_id,
            state=derive_state(expected_scenes, completed_scenes),
            max_scenes=max_scenes,
            expected_scenes=expected_scenes,
            completed_scenes=completed_scenes,
            created_at=created_at,
        )

    def list_descriptions(self, job_id: UUID) -> list[SceneDescription]:
        self.get_job(job_id)  # raises NotFoundError, so an unknown job isn't reported as "no descriptions"
        with self._get_pool().connection() as conn:
            rows = conn.execute(
                """
                SELECT scene_token, scene_name, camera_channel, image_path, description, model_name, generated_at
                FROM scene_descriptions WHERE job_id = %s ORDER BY scene_name
                """,
                (job_id,),
            ).fetchall()
        return [
            SceneDescription(
                scene_token=token,
                scene_name=name,
                camera_channel=channel,
                image_path=path,
                description=text,
                model_name=model,
                generated_at=generated_at,
            )
            for token, name, channel, path, text, model, generated_at in rows
        ]

    def healthcheck(self) -> bool:
        import psycopg
        from psycopg_pool import PoolTimeout

        try:
            with self._get_pool().connection() as conn:
                conn.execute("SELECT 1")
        except (psycopg.Error, PoolTimeout) as exc:
            logger.warning("postgres unreachable: {}", exc)
            return False
        return True

    def _get_pool(self) -> Any:
        if self._pool is None:
            from psycopg_pool import ConnectionPool

            with self._lock:
                if self._pool is None:
                    pool = ConnectionPool(self._database_url, min_size=1, max_size=4, open=False)
                    pool.open(wait=True, timeout=10)
                    self._pool = pool
        return self._pool
