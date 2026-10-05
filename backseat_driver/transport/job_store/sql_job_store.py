"""SQL adapter for the `JobStore` port: maps persistence rows (`orm.py`/`storage.py`) to domain models.

Postgres when distributed; the monolith runs the same code over a SQLite file so its jobs survive a restart."""

from uuid import UUID

from sqlalchemy.exc import IntegrityError

from backseat_driver.errors import IdempotencyKeyInUseError, NotFoundError
from backseat_driver.models import DeadLetter, Job, JobDeadLetter, JobState, SceneDescription
from backseat_driver.transport.job_store.job_store import JobStore, derive_state
from backseat_driver.write.job_store.orm import JobRow
from backseat_driver.write.job_store.storage import JobStorage


class SqlJobStore(JobStore):
    def __init__(self, storage: JobStorage) -> None:
        self._storage = storage

    async def ensure_schema(self) -> None:
        await self._storage.ensure_schema()

    async def close(self) -> None:
        await self._storage.close()

    async def create_job(
        self, job_id: UUID, max_scenes: int | None, transaction_id: str, idempotency_key: str | None = None
    ) -> None:
        try:
            await self._storage.insert_job(job_id, max_scenes, transaction_id, idempotency_key)
        except IntegrityError as exc:
            # The unique constraint is what makes two concurrent requests with one key safe, but an IntegrityError
            # says nothing about which constraint it was, so confirm the key is taken before blaming it.
            if idempotency_key is not None and await self._storage.fetch_job_by_key(idempotency_key) is not None:
                raise IdempotencyKeyInUseError(idempotency_key) from exc
            raise

    async def find_job_by_idempotency_key(self, idempotency_key: str) -> Job | None:
        found = await self._storage.fetch_job_by_key(idempotency_key)
        return None if found is None else _to_job(*found)

    async def set_expected_scenes(self, job_id: UUID, expected_scenes: int) -> None:
        if not await self._storage.update_expected_scenes(job_id, expected_scenes):
            raise NotFoundError(f"job {job_id} not found")

    async def fail_job(self, job_id: UUID, error: str) -> None:
        if not await self._storage.update_error(job_id, error):
            raise NotFoundError(f"job {job_id} not found")

    async def record_dead_letter(self, job_id: UUID | None, dead_letter: DeadLetter) -> None:
        if job_id is not None:
            await self.get_job(job_id)  # raises NotFoundError rather than a foreign key violation
        await self._storage.insert_dead_letter(job_id, dead_letter.model_dump())

    async def list_dead_letters(self, job_id: UUID) -> list[DeadLetter]:
        await self.get_job(job_id)
        return [
            DeadLetter(
                task=row.task,  # ty: ignore[invalid-argument-type]
                payload=row.payload,
                error=row.error,
                failed_at=row.failed_at,
            )
            for row in await self._storage.fetch_dead_letters(job_id)
        ]

    async def list_recent_dead_letters(self, limit: int) -> list[JobDeadLetter]:
        return [
            JobDeadLetter(
                job_id=row.job_id,
                task=row.task,  # ty: ignore[invalid-argument-type]
                payload=row.payload,
                error=row.error,
                failed_at=row.failed_at,
            )
            for row in await self._storage.fetch_recent_dead_letters(limit)
        ]

    async def record_description(self, job_id: UUID, description: SceneDescription) -> None:
        try:
            await self._storage.insert_description(job_id, description.model_dump())
        except IntegrityError as exc:
            # A redelivery is absorbed by ON CONFLICT DO NOTHING, so the foreign key is the likely culprit; confirm it.
            if await self._storage.fetch_job(job_id) is None:
                raise NotFoundError(f"job {job_id} not found") from exc
            raise

    async def get_job(self, job_id: UUID) -> Job:
        found = await self._storage.fetch_job(job_id)
        if found is None:
            raise NotFoundError(f"job {job_id} not found")

        return _to_job(*found)

    async def list_jobs(self, state: JobState | None = None, limit: int | None = None) -> list[Job]:
        return [_to_job(row, completed) for row, completed in await self._storage.fetch_jobs(state, limit)]

    async def list_descriptions(self, job_id: UUID) -> list[SceneDescription]:
        await self.get_job(job_id)  # raises NotFoundError, so an unknown job isn't reported as "no descriptions"
        return [
            SceneDescription(
                scene_token=row.scene_token,
                scene_name=row.scene_name,
                camera_channel=row.camera_channel,
                image_path=row.image_path,
                description=row.description,
                model_name=row.model_name,
                reference_description=row.reference_description,
                generated_at=row.generated_at,
            )
            for row in await self._storage.fetch_descriptions(job_id)
        ]

    async def healthcheck(self) -> bool:
        return await self._storage.ping()


def _to_job(job: JobRow, completed_scenes: int) -> Job:
    return Job(
        job_id=job.job_id,
        transaction_id=job.transaction_id,
        state=derive_state(job.expected_scenes, completed_scenes, job.error),
        max_scenes=job.max_scenes,
        expected_scenes=job.expected_scenes,
        completed_scenes=completed_scenes,
        created_at=job.created_at,
        error=job.error,
    )
