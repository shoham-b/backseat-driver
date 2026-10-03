"""In-memory test doubles — no broker, no database, no model."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from backseat_driver.captioning.captioner import Captioner
from backseat_driver.captioning.http_client import HttpClient
from backseat_driver.config import Settings
from backseat_driver.errors import NotFoundError
from backseat_driver.jobs.job_queue import JobQueue
from backseat_driver.jobs.job_store import JobStore, derive_state
from backseat_driver.models import CaptionTask, IngestTask, Job, SceneDescription, SceneKeyframe
from backseat_driver.scenes.scene_loader import SceneLoader


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


def make_settings(**overrides: Any) -> Settings:
    """Settings straight from keyword arguments, ignoring any .env file, so tests never touch the environment."""
    return Settings(_env_file=None, **overrides)


def make_keyframe(n: int) -> SceneKeyframe:
    return SceneKeyframe(
        scene_token=f"token-{n}",
        scene_name=f"scene-{n:04d}",
        camera_channel="CAM_FRONT",
        image_path=f"/img/{n}.jpg",
    )


@dataclass(frozen=True)
class PostedJson:
    url: str
    payload: dict[str, Any]
    headers: dict[str, str]
    timeout: float
    service: str


@dataclass(frozen=True)
class Probe:
    url: str
    headers: dict[str, str]
    timeout: float


class FakeHttpClient(HttpClient):
    """Answers `post_json` with a canned body (or raises) and `is_reachable` with a canned flag, recording each call."""

    def __init__(self, response: dict[str, Any] | None = None, error: Exception | None = None, reachable: bool = True):
        self.posts: list[PostedJson] = []
        self.probes: list[Probe] = []
        self._response = response if response is not None else {}
        self._error = error
        self._reachable = reachable

    def post_json(
        self, url: str, payload: dict[str, Any], headers: dict[str, str], timeout: float, service: str
    ) -> dict[str, Any]:
        self.posts.append(PostedJson(url, payload, headers, timeout, service))
        if self._error:
            raise self._error
        return self._response

    def is_reachable(self, url: str, headers: dict[str, str], timeout: float) -> bool:
        self.probes.append(Probe(url, headers, timeout))
        return self._reachable
