"""In-memory implementation of the `JobStore` port — the monolith's store, so local dev needs no database.

State lives in the process and is lost on restart; `SqlJobStore` over SQLite is what the monolith uses by default,
so its jobs outlive a restart. This one backs tests and `BACKSEAT_DRIVER_JOBS_DB_PATH=` (empty).
"""

from datetime import UTC, datetime
from threading import Lock
from uuid import UUID

from backseat_driver.errors import NotFoundError
from backseat_driver.models import Job, SceneDescription
from backseat_driver.write.job_store.job_store import JobStore, derive_state


class _Record:
    def __init__(self, max_scenes: int | None, transaction_id: str, idempotency_key: str | None) -> None:
        self.max_scenes = max_scenes
        self.transaction_id = transaction_id
        self.idempotency_key = idempotency_key
        self.expected_scenes: int | None = None
        self.error: str | None = None
        self.created_at = datetime.now(UTC)
        self.descriptions: dict[str, SceneDescription] = {}


class InMemoryJobStore(JobStore):
    def __init__(self) -> None:
        # The API's request threads and the in-process worker thread share this store.
        self._lock = Lock()
        self._jobs: dict[UUID, _Record] = {}

    def create_job(
        self, job_id: UUID, max_scenes: int | None, transaction_id: str, idempotency_key: str | None = None
    ) -> None:
        with self._lock:
            if idempotency_key is not None and self._job_id_for(idempotency_key) is not None:
                raise ValueError(f"idempotency key {idempotency_key!r} is already used")
            self._jobs[job_id] = _Record(max_scenes, transaction_id, idempotency_key)

    def find_job_by_idempotency_key(self, idempotency_key: str) -> Job | None:
        with self._lock:
            job_id = self._job_id_for(idempotency_key)
            return None if job_id is None else self._to_job(job_id, self._jobs[job_id])

    def _job_id_for(self, idempotency_key: str) -> UUID | None:
        return next((job_id for job_id, r in self._jobs.items() if r.idempotency_key == idempotency_key), None)

    def set_expected_scenes(self, job_id: UUID, expected_scenes: int) -> None:
        with self._lock:
            self._get(job_id).expected_scenes = expected_scenes

    def fail_job(self, job_id: UUID, error: str) -> None:
        with self._lock:
            record = self._get(job_id)
            record.error = record.error or error

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
            state=derive_state(record.expected_scenes, completed, record.error),
            max_scenes=record.max_scenes,
            expected_scenes=record.expected_scenes,
            completed_scenes=completed,
            created_at=record.created_at,
            error=record.error,
        )

    def _get(self, job_id: UUID) -> _Record:
        if job_id not in self._jobs:
            raise NotFoundError(f"job {job_id} not found")
        return self._jobs[job_id]
