"""In-memory test doubles — no broker, no database, no model, no network, no real server."""

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from backseat_driver.captioning.captioner import Captioner
from backseat_driver.cli.context import CliContext
from backseat_driver.config import Settings, VlmBackend
from backseat_driver.errors import NotFoundError
from backseat_driver.jobs.job_queue import JobQueue
from backseat_driver.jobs.job_store import JobStore, derive_state
from backseat_driver.logger import LogFormat
from backseat_driver.models import CaptionTask, IngestTask, Job, SceneDescription, SceneKeyframe
from backseat_driver.scenes.dataset_cache import DatasetCache
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


class FakeDatasetCache(DatasetCache):
    """Never touches the network or the disk; records which (dataroot, version) it was asked to ensure."""

    def __init__(self) -> None:
        self.ensured: list[tuple[str, str]] = []

    def ensure(self, dataroot: str, version: str) -> None:
        self.ensured.append((dataroot, version))


class FakeLoaderFactory:
    """Stands in for `CliContext.build_loader`: hands out a fake loader and records the arguments."""

    def __init__(self, keyframes: list[SceneKeyframe]) -> None:
        self._keyframes = keyframes
        self.calls: list[tuple[str, str, str]] = []

    def __call__(self, dataroot: str, version: str, camera_channel: str) -> SceneLoader:
        self.calls.append((dataroot, version, camera_channel))
        return FakeSceneLoader(self._keyframes)


class FakeCaptionerFactory:
    """Stands in for `CliContext.build_captioner`: hands out one captioner and records the arguments."""

    def __init__(self, captioner: Captioner) -> None:
        self._captioner = captioner
        self.calls: list[tuple[Settings, VlmBackend | None, str | None]] = []

    def __call__(self, settings: Settings, backend: VlmBackend | None, model_name: str | None) -> Captioner:
        self.calls.append((settings, backend, model_name))
        return self._captioner


class FakeLogging:
    """Stands in for `setup_logging`, which would replace loguru's sinks for the whole test process."""

    def __init__(self) -> None:
        self.calls: list[tuple[LogFormat, str]] = []

    def __call__(self, fmt: LogFormat, service: str) -> None:
        self.calls.append((fmt, service))


class FakeSchemaInit:
    def __init__(self, error: Exception | None = None) -> None:
        self.urls: list[str] = []
        self._error = error

    def __call__(self, database_url: str) -> None:
        self.urls.append(database_url)
        if self._error:
            raise self._error


class FakeWorkerHost:
    """Records what a worker command did, in order: model load, then the queue it started consuming."""

    def __init__(self, load_error: Exception | None = None) -> None:
        self.events: list[str] = []
        self.argv: list[str] = []
        self._load_error = load_error

    def load_model(self) -> None:
        if self._load_error:
            raise self._load_error
        self.events.append("load")

    def start(self, argv: list[str]) -> None:
        self.argv = argv
        self.events.append(argv[argv.index("-Q") + 1])


class FakePytestRunner:
    def __init__(self, exit_code: int = 0, error: Exception | None = None) -> None:
        self.calls: list[tuple[list[str], str | None]] = []
        self._exit_code = exit_code
        self._error = error

    def __call__(self, args: list[str], api_url: str | None) -> int:
        self.calls.append((args, api_url))
        if self._error:
            raise self._error
        return self._exit_code


class FakeServer:
    """Stands in for the `ui` web server: keeps what it was asked to serve and the page, then returns (or Ctrl+C)."""

    def __init__(self, interrupt: bool = True) -> None:
        self.calls: list[tuple[str, int, str | None]] = []  # host, port, URL to open
        self.html = ""
        self._interrupt = interrupt

    def __call__(self, directory: str, host: str, port: int, open_url: str | None) -> None:
        self.calls.append((host, port, open_url))
        self.html = (Path(directory) / "index.html").read_text(encoding="utf-8")  # the directory is temporary
        if self._interrupt:
            raise KeyboardInterrupt


def make_settings(**overrides: Any) -> Settings:
    """Settings straight from keyword arguments, ignoring any .env file, so tests never touch the environment."""
    return Settings(_env_file=None, **overrides)


def make_cli_context(**overrides: Any) -> CliContext:
    """A `CliContext` of fakes; pass the pieces a test cares about (and wants to inspect) as keyword arguments."""
    worker = FakeWorkerHost()
    base = CliContext(
        settings=make_settings(),
        configure_logging=FakeLogging(),
        dataset_cache=FakeDatasetCache(),
        build_loader=FakeLoaderFactory([]),
        build_captioner=FakeCaptionerFactory(FakeCaptioner()),
        init_schema=FakeSchemaInit(),
        load_caption_model=worker.load_model,
        start_worker=worker.start,
        run_pytest=FakePytestRunner(),
        serve=FakeServer(),
    )
    return replace(base, **overrides)


def make_keyframe(n: int) -> SceneKeyframe:
    return SceneKeyframe(
        scene_token=f"token-{n}",
        scene_name=f"scene-{n:04d}",
        camera_channel="CAM_FRONT",
        image_path=f"/img/{n}.jpg",
    )
