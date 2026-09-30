"""In-memory test doubles for the distributed mode — no broker, no database, no model."""

from collections import defaultdict
from collections.abc import Mapping
from datetime import UTC, datetime
from uuid import UUID

from vlmscene.bl.errors import NotFoundError
from vlmscene.bl.job_queue import MessageHandler
from vlmscene.bl.job_store import derive_state
from vlmscene.models import Job, SceneDescription, SceneKeyframe


class FakeJobQueue:
    def __init__(self, healthy: bool = True) -> None:
        self.healthy = healthy
        self.published: list[tuple[str, bytes, Mapping[str, str]]] = []
        self._pending: dict[str, list[tuple[bytes, Mapping[str, str]]]] = defaultdict(list)

    def publish(self, queue: str, body: bytes, headers: Mapping[str, str] | None = None) -> None:
        self.published.append((queue, body, headers or {}))
        self._pending[queue].append((body, headers or {}))

    def consume(self, queue: str, handler: MessageHandler, prefetch: int = 1) -> None:
        """Deliver everything queued so far, then return (the real consume blocks forever)."""
        while self._pending[queue]:
            body, headers = self._pending[queue].pop(0)
            handler(body, headers)

    def healthcheck(self) -> bool:
        return self.healthy


class FakeJobStore:
    def __init__(self, healthy: bool = True) -> None:
        self.healthy = healthy
        self._jobs: dict[UUID, tuple[int | None, int | None, datetime]] = {}
        self._descriptions: dict[UUID, dict[str, SceneDescription]] = {}

    def create_job(self, job_id: UUID, max_scenes: int | None) -> None:
        self._jobs[job_id] = (max_scenes, None, datetime.now(UTC))
        self._descriptions[job_id] = {}

    def set_expected_scenes(self, job_id: UUID, expected_scenes: int) -> None:
        max_scenes, _, created_at = self._get(job_id)
        self._jobs[job_id] = (max_scenes, expected_scenes, created_at)

    def record_description(self, job_id: UUID, description: SceneDescription) -> None:
        self._get(job_id)
        self._descriptions[job_id].setdefault(description.scene_token, description)

    def get_job(self, job_id: UUID) -> Job:
        max_scenes, expected_scenes, created_at = self._get(job_id)
        completed = len(self._descriptions[job_id])
        return Job(
            job_id=job_id,
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

    def _get(self, job_id: UUID) -> tuple[int | None, int | None, datetime]:
        if job_id not in self._jobs:
            raise NotFoundError(f"job {job_id} not found")
        return self._jobs[job_id]


class FakeSceneLoader:
    def __init__(self, keyframes: list[SceneKeyframe]) -> None:
        self._keyframes = keyframes

    def load_keyframes(self) -> list[SceneKeyframe]:
        return self._keyframes


class FakeCaptioner:
    model_name = "fake-model"

    def load(self) -> None:
        pass

    def caption(self, image_path: str) -> str:
        return f"a caption for {image_path}"

    def healthcheck(self) -> bool:
        return True


def make_keyframe(n: int) -> SceneKeyframe:
    return SceneKeyframe(
        scene_token=f"token-{n}",
        scene_name=f"scene-{n:04d}",
        camera_channel="CAM_FRONT",
        image_path=f"/img/{n}.jpg",
    )
