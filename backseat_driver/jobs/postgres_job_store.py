"""Postgres adapter for the `JobStore` port: maps persistence rows (`orm.py`/`storage.py`) to domain models."""

from uuid import UUID

from backseat_driver.errors import NotFoundError
from backseat_driver.jobs.job_store import JobStore, derive_state
from backseat_driver.jobs.storage import JobStorage
from backseat_driver.models import Job, SceneDescription


class PostgresJobStore(JobStore):
    def __init__(self, database_url: str) -> None:
        self._storage = JobStorage(database_url)

    def ensure_schema(self) -> None:
        self._storage.ensure_schema()

    def create_job(self, job_id: UUID, max_scenes: int | None, transaction_id: str) -> None:
        self._storage.insert_job(job_id, max_scenes, transaction_id)

    def set_expected_scenes(self, job_id: UUID, expected_scenes: int) -> None:
        if not self._storage.update_expected_scenes(job_id, expected_scenes):
            raise NotFoundError(f"job {job_id} not found")

    def record_description(self, job_id: UUID, description: SceneDescription) -> None:
        # The nuScenes reference label is only used by the CLI report; the table has no column for it.
        self._storage.insert_description(job_id, description.model_dump(exclude={"reference_description"}))

    def get_job(self, job_id: UUID) -> Job:
        found = self._storage.fetch_job(job_id)
        if found is None:
            raise NotFoundError(f"job {job_id} not found")

        job, completed_scenes = found
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
            for row in self._storage.fetch_descriptions(job_id)
        ]

    def healthcheck(self) -> bool:
        return self._storage.ping()
