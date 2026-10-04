"""In-memory implementation of the `JobStore` port — the monolith's store, so local dev needs no database.

State lives in the process and is lost on restart; `SqlJobStore` over SQLite is what the monolith uses by default,
so its jobs outlive a restart. This one backs tests and `BACKSEAT_DRIVER_JOBS_DB_PATH=` (empty).
"""

from datetime import UTC, datetime
from threading import Lock
from uuid import UUID

from backseat_driver.errors import NotFoundError
from backseat_driver.jobs.job_store import JobStore, derive_state
from backseat_driver.models import Job, SceneDescription


class _Record:
    def __init__(self, max_scenes: int | None, transaction_id: str) -> None:
        self.max_scenes = max_scenes
        self.transaction_id = transaction_id
        self.expected_scenes: int | None = None
        self.created_at = datetime.now(UTC)
        self.descriptions: dict[str, SceneDescription] = {}


class InMemoryJobStore(JobStore):
    def __init__(self) -> None:
        # The API's request threads and the in-process worker thread share this store.
        self._lock = Lock()
        self._jobs: dict[UUID, _Record] = {}

    def create_job(self, job_id: UUID, max_scenes: int | None, transaction_id: str) -> None:
        with self._lock:
            self._jobs[job_id] = _Record(max_scenes, transaction_id)

    def set_expected_scenes(self, job_id: UUID, expected_scenes: int) -> None:
        with self._lock:
            self._get(job_id).expected_scenes = expected_scenes

    def record_description(self, job_id: UUID, description: SceneDescription) -> None:
        with self._lock:
            self._get(job_id).descriptions.setdefault(description.scene_token, description)

    def get_job(self, job_id: UUID) -> Job:
        with self._lock:
            return self._to_job(job_id, self._get(job_id))

    def list_jobs(self) -> list[Job]:
        with self._lock:
            jobs = [self._to_job(job_id, record) for job_id, record in reversed(self._jobs.items())]
        # Stable, so jobs the clock cannot tell apart keep newest-first from the reversed insertion order.
        return sorted(jobs, key=lambda job: job.created_at, reverse=True)

    def list_descriptions(self, job_id: UUID) -> list[SceneDescription]:
        with self._lock:
            return sorted(self._get(job_id).descriptions.values(), key=lambda d: d.scene_name)

    def healthcheck(self) -> bool:
        return True

    @staticmethod
    def _to_job(job_id: UUID, record: _Record) -> Job:
        completed = len(record.descriptions)
        return Job(
            job_id=job_id,
            transaction_id=record.transaction_id,
            state=derive_state(record.expected_scenes, completed),
            max_scenes=record.max_scenes,
            expected_scenes=record.expected_scenes,
            completed_scenes=completed,
            created_at=record.created_at,
        )

    def _get(self, job_id: UUID) -> _Record:
        if job_id not in self._jobs:
            raise NotFoundError(f"job {job_id} not found")
        return self._jobs[job_id]
