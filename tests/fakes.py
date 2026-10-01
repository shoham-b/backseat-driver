"""In-memory test doubles for the distributed mode — no broker, no database, no model."""

from datetime import UTC, datetime
from uuid import UUID

from backseat_driver.bl.captioner import Captioner
from backseat_driver.bl.errors import NotFoundError
from backseat_driver.bl.job_queue import JobQueue
from backseat_driver.bl.job_store import JobStore, derive_state
from backseat_driver.bl.scene_loader import SceneLoader
from backseat_driver.models import CaptionTask, IngestTask, Job, SceneDescription, SceneKeyframe


class FakeJobQueue(JobQueue):
    def __init__(self, healthy: bool = True) -> None:
        self.healthy = healthy
        self.ingest_tasks: list[IngestTask] = []
        self.caption_tasks: list[CaptionTask] = []

    def enqueue_ingest(self, task: IngestTask) -> None:
        self.ingest_tasks.append(task)

    def enqueue_caption(self, task: CaptionTask) -> None:
        self.caption_tasks.append(task)

    def healthcheck(self) -> bool:
        return self.healthy


class FakeJobStore(JobStore):
    def __init__(self, healthy: bool = True) -> None:
        self.healthy = healthy
        self._jobs: dict[UUID, tuple[str, int | None, int | None, datetime]] = {}
        self._descriptions: dict[UUID, dict[str, SceneDescription]] = {}

    def create_job(self, job_id: UUID, max_scenes: int | None, transaction_id: str) -> None:
        self._jobs[job_id] = (transaction_id, max_scenes, None, datetime.now(UTC))
        self._descriptions[job_id] = {}

    def set_expected_scenes(self, job_id: UUID, expected_scenes: int) -> None:
        transaction_id, max_scenes, _, created_at = self._get(job_id)
        self._jobs[job_id] = (transaction_id, max_scenes, expected_scenes, created_at)

    def record_description(self, job_id: UUID, description: SceneDescription) -> None:
        self._get(job_id)
        self._descriptions[job_id].setdefault(description.scene_token, description)

    def get_job(self, job_id: UUID) -> Job:
        transaction_id, max_scenes, expected_scenes, created_at = self._get(job_id)
        completed = len(self._descriptions[job_id])
        return Job(
            job_id=job_id,
            transaction_id=transaction_id,
            state=derive_state(expected_scenes, completed),
            max_scenes=max_scenes,
            expected_scenes=expected_scenes,
            completed_scenes=completed,
            created_at=created_at,
        )

    def list_descriptions(self, job_id: UUID) -> list[SceneDescription]:
        self._get(job_id)
        return sorted(self._descriptions[job_id].values(), key=lambda d: d.scene_name)

    def healthcheck(self) -> bool:
        return self.healthy

    def _get(self, job_id: UUID) -> tuple[str, int | None, int | None, datetime]:
        if job_id not in self._jobs:
            raise NotFoundError(f"job {job_id} not found")
        return self._jobs[job_id]


class FakeSceneLoader(SceneLoader):
    def __init__(self, keyframes: list[SceneKeyframe]) -> None:
        self._keyframes = keyframes

    def load_keyframes(self) -> list[SceneKeyframe]:
        return self._keyframes


class FakeCaptioner(Captioner):
    """Returns a canned caption (default: derived from the path) and records the paths it saw."""

    def __init__(self, caption_text: str | None = None) -> None:
        self._caption_text = caption_text
        self.seen_paths: list[str] = []

    @property
    def model_name(self) -> str:
        return "fake-model"

    def load(self) -> None:
        pass

    def caption(self, image_path: str) -> str:
        self.seen_paths.append(image_path)
        return self._caption_text or f"a caption for {image_path}"

    def healthcheck(self) -> bool:
        return True


def make_keyframe(n: int) -> SceneKeyframe:
    return SceneKeyframe(
        scene_token=f"token-{n}",
        scene_name=f"scene-{n:04d}",
        camera_channel="CAM_FRONT",
        image_path=f"/img/{n}.jpg",
    )
