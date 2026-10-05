"""In-memory implementation of the `JobStore` port — the monolith's store, so local dev needs no database.

State lives in the process and is lost on restart; `SqlJobStore` over SQLite is what the monolith uses by default,
so its jobs outlive a restart. This one backs tests and `BACKSEAT_DRIVER_JOBS_DB_PATH=` (empty).
"""

from collections.abc import Callable
from datetime import datetime
from threading import Lock
from uuid import UUID

from backseat_driver.errors import IdempotencyKeyInUseError, NotFoundError
from backseat_driver.models import DeadLetter, Job, JobDeadLetter, JobState, SceneDescription
from backseat_driver.transport.job_store.job_store import JobStore, derive_state
from backseat_driver.write.job_store.creation_clock import CreationClock


class _Record:
    def __init__(
        self, max_scenes: int | None, transaction_id: str, idempotency_key: str | None, created_at: datetime
    ) -> None:
        self.max_scenes = max_scenes
        self.transaction_id = transaction_id
        self.idempotency_key = idempotency_key
        self.expected_scenes: int | None = None
        self.error: str | None = None
        self.created_at = created_at
        self.descriptions: dict[tuple[str, str], SceneDescription] = {}
        self.dead_letters: list[DeadLetter] = []


class InMemoryJobStore(JobStore):
    def __init__(self, clock: Callable[[], datetime] | None = None) -> None:
        self._clock = clock or CreationClock()
        # The API's request threads and the in-process worker thread share this store.
        self._lock = Lock()
        self._jobs: dict[UUID, _Record] = {}
        self._recent: list[JobDeadLetter] = []  # every dead letter in arrival order, for the cross-job listing

    def create_job(
        self, job_id: UUID, max_scenes: int | None, transaction_id: str, idempotency_key: str | None = None
    ) -> None:
        with self._lock:
            if idempotency_key is not None and self._job_id_for(idempotency_key) is not None:
                raise IdempotencyKeyInUseError(idempotency_key)
            self._jobs[job_id] = _Record(max_scenes, transaction_id, idempotency_key, self._clock())

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

    def record_dead_letter(self, job_id: UUID | None, dead_letter: DeadLetter) -> None:
        with self._lock:
            if job_id is not None:
                self._get(job_id).dead_letters.append(dead_letter)
            self._recent.append(JobDeadLetter(job_id=job_id, **dead_letter.model_dump()))

    def list_recent_dead_letters(self, limit: int) -> list[JobDeadLetter]:
        with self._lock:
            return self._recent[::-1][:limit]

    def list_dead_letters(self, job_id: UUID) -> list[DeadLetter]:
        with self._lock:
            return list(self._get(job_id).dead_letters)

    def record_description(self, job_id: UUID, description: SceneDescription) -> None:
        key = (description.scene_token, description.camera_channel)
        with self._lock:
            self._get(job_id).descriptions.setdefault(key, description)

    def get_job(self, job_id: UUID) -> Job:
        with self._lock:
            return self._to_job(job_id, self._get(job_id))

    def list_jobs(self, state: JobState | None = None, limit: int | None = None) -> list[Job]:
        with self._lock:
            jobs = [self._to_job(job_id, record) for job_id, record in self._jobs.items()]
        newest_first = sorted(jobs, key=lambda job: job.created_at, reverse=True)
        return [job for job in newest_first if state is None or job.state is state][:limit]

    def list_descriptions(self, job_id: UUID) -> list[SceneDescription]:
        with self._lock:
            return sorted(self._get(job_id).descriptions.values(), key=lambda d: (d.scene_name, d.camera_channel))

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
