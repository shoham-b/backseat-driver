"""In-memory test doubles — no broker, no database, no model."""

from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager, nullcontext
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import UUID

from pydantic_settings import BaseSettings, PydanticBaseSettingsSource

from backseat_driver.config import Settings
from backseat_driver.errors import IdempotencyKeyInUseError, NotFoundError
from backseat_driver.models import (
    CaptionTask,
    DeadLetter,
    IngestTask,
    Job,
    JobDeadLetter,
    SceneDescription,
    SceneKeyframe,
)
from backseat_driver.process.captioner import Captioner
from backseat_driver.process.http_client import HttpClient, HttpResponse
from backseat_driver.read.dataset.scene_loader import SceneLoader
from backseat_driver.read.images.image_store import ImageStore
from backseat_driver.read.s3.dataset_store import DatasetStore
from backseat_driver.show.description_source import DescriptionSource
from backseat_driver.transport.job_queue import JobQueue
from backseat_driver.transport.job_store.job_store import JobStore, derive_state


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
        self._descriptions: dict[UUID, dict[tuple[str, str], SceneDescription]] = {}
        self._errors: dict[UUID, str] = {}
        self._keys: dict[str, UUID] = {}
        self._dead_letters: dict[UUID, list[DeadLetter]] = {}
        self._recent: list[JobDeadLetter] = []

    def record_dead_letter(self, job_id: UUID | None, dead_letter: DeadLetter) -> None:
        if job_id is not None:
            self._get(job_id)
            self._dead_letters.setdefault(job_id, []).append(dead_letter)
        self._recent.append(JobDeadLetter(job_id=job_id, **dead_letter.model_dump()))

    def list_recent_dead_letters(self, limit: int) -> list[JobDeadLetter]:
        return self._recent[::-1][:limit]

    def list_dead_letters(self, job_id: UUID) -> list[DeadLetter]:
        self._get(job_id)
        return list(self._dead_letters.get(job_id, []))

    def create_job(
        self, job_id: UUID, max_scenes: int | None, transaction_id: str, idempotency_key: str | None = None
    ) -> None:
        if idempotency_key is not None:
            if idempotency_key in self._keys:
                raise IdempotencyKeyInUseError(idempotency_key)
            self._keys[idempotency_key] = job_id
        self._jobs[job_id] = (transaction_id, max_scenes, None, datetime.now(UTC))
        self._descriptions[job_id] = {}

    def set_expected_scenes(self, job_id: UUID, expected_scenes: int) -> None:
        transaction_id, max_scenes, _, created_at = self._get(job_id)
        self._jobs[job_id] = (transaction_id, max_scenes, expected_scenes, created_at)

    def find_job_by_idempotency_key(self, idempotency_key: str) -> Job | None:
        job_id = self._keys.get(idempotency_key)
        return None if job_id is None else self.get_job(job_id)

    def fail_job(self, job_id: UUID, error: str) -> None:
        self._get(job_id)
        self._errors.setdefault(job_id, error)

    def record_description(self, job_id: UUID, description: SceneDescription) -> None:
        self._get(job_id)
        self._descriptions[job_id].setdefault((description.scene_token, description.camera_channel), description)

    def get_job(self, job_id: UUID) -> Job:
        transaction_id, max_scenes, expected_scenes, created_at = self._get(job_id)
        completed = len(self._descriptions[job_id])
        return Job(
            job_id=job_id,
            transaction_id=transaction_id,
            state=derive_state(expected_scenes, completed, self._errors.get(job_id)),
            max_scenes=max_scenes,
            expected_scenes=expected_scenes,
            completed_scenes=completed,
            created_at=created_at,
            error=self._errors.get(job_id),
        )

    def list_jobs(self) -> list[Job]:
        jobs = [self.get_job(job_id) for job_id in reversed(self._jobs)]
        return sorted(jobs, key=lambda job: job.created_at, reverse=True)

    def list_descriptions(self, job_id: UUID) -> list[SceneDescription]:
        self._get(job_id)
        return sorted(self._descriptions[job_id].values(), key=lambda d: (d.scene_name, d.camera_channel))

    def healthcheck(self) -> bool:
        return self.healthy

    def _get(self, job_id: UUID) -> tuple[str, int | None, int | None, datetime]:
        if job_id not in self._jobs:
            raise NotFoundError(f"job {job_id} not found")
        return self._jobs[job_id]


class FakeImageStore(ImageStore):
    """Addresses images by made-up URIs and hands out a made-up local path, without touching the filesystem."""

    def __init__(self) -> None:
        self.opened: list[str] = []
        self.released: list[str] = []

    def uri_for(self, key: str) -> str:
        return f"fake://{key}"

    @contextmanager
    def local_copy(self, uri: str) -> Iterator[Path]:
        self.opened.append(uri)
        try:
            yield Path("/fetched") / PurePosixPath(uri).name
        finally:
            self.released.append(uri)


class PassthroughImageStore(ImageStore):
    """Hands every key back as its own path with no bookkeeping, so a benchmark times the code under test and not
    the fake."""

    def uri_for(self, key: str) -> str:
        return key

    def local_copy(self, uri: str) -> AbstractContextManager[Path]:
        return nullcontext(_PASSTHROUGH_PATH)


_PASSTHROUGH_PATH = Path("/fetched")


class FakeDatasetStore(FakeImageStore, DatasetStore):
    """An in-memory dataset bucket: keys map to the local file that was uploaded under them."""

    def __init__(self, objects: dict[str, Path] | None = None) -> None:
        super().__init__()
        self.objects: dict[str, Path] = objects or {}
        self.uploads: list[str] = []
        self.downloaded_prefixes: list[tuple[str, Path]] = []

    def exists(self, key: str) -> bool:
        return key in self.objects

    def upload(self, key: str, path: Path) -> None:
        self.objects[key] = path
        self.uploads.append(key)

    def download_prefix(self, prefix: str, directory: Path) -> None:
        self.downloaded_prefixes.append((prefix, directory))


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


class _KeywordSettings(Settings):
    """`Settings` whose only source is its keyword arguments, so neither an environment variable nor a `.env` file can
    change a field. `_env_file=None` alone leaves the variables `just` exports, and a module that builds its app at
    import time runs before any fixture could hide them."""

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (init_settings,)


def keyword_settings(**values: Any) -> Settings:
    """Settings with exactly the given values, ignoring the environment and any .env file; every other field keeps
    its default in the code, which is what a test of those defaults needs."""
    return _KeywordSettings(**values)


def make_settings(**overrides: Any) -> Settings:
    """`keyword_settings` plus what a test of the running service needs.

    A model is chosen for every backend, since building a captioner without one fails on purpose.
    """
    models: dict[str, Any] = {
        # The monolith keeps jobs in memory, not in a SQLite file in the working directory.
        "jobs_db_path": "",
        "vlm_model_name": "fake-model",
        "ollama_model_name": "fake-model",
        "anthropic_model_name": "fake-model",
    }
    return keyword_settings(**{**models, **overrides})


def make_image_uri(n: int) -> str:
    return FakeImageStore().uri_for(make_keyframe(n).image_path)


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
        self.gets: list[Probe] = []
        self.responses_by_url: dict[str, HttpResponse] = {}
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

    def get(self, url: str, headers: dict[str, str], timeout: float, service: str) -> HttpResponse:
        self.gets.append(Probe(url, headers, timeout))
        if self._error:
            raise self._error
        return self.responses_by_url[url]

    def is_reachable(self, url: str, headers: dict[str, str], timeout: float) -> bool:
        self.probes.append(Probe(url, headers, timeout))
        return self._reachable


class FakeDescriptionSource(DescriptionSource):
    """Serves canned descriptions and an image body made of the `image_path`; links images only given a prefix."""

    def __init__(self, descriptions: list[SceneDescription], link_prefix: str | None = None) -> None:
        self._descriptions = descriptions
        self._link_prefix = link_prefix

    def descriptions(self) -> list[SceneDescription]:
        return self._descriptions

    def image(self, image_path: str) -> HttpResponse:
        return HttpResponse(image_path.encode(), "image/test")

    def image_link(self, image_path: str) -> str | None:
        return None if self._link_prefix is None else f"{self._link_prefix}{image_path}"


class FakeCeleryConnection:
    def __init__(self, error: Exception | None = None) -> None:
        self.ensure_calls: list[int] = []
        self._error = error

    def __enter__(self) -> "FakeCeleryConnection":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def ensure_connection(self, max_retries: int) -> None:
        self.ensure_calls.append(max_retries)
        if self._error:
            raise self._error


class FakeCeleryApp:
    """Duck-types the slice of `celery.Celery` that `CeleryJobQueue` uses, recording what was published."""

    def __init__(self, publish_error: Exception | None = None, connection: FakeCeleryConnection | None = None) -> None:
        self.sent: list[tuple[str, list[Any]]] = []
        self.connection = connection or FakeCeleryConnection()
        self._publish_error = publish_error

    def send_task(self, name: str, args: list[Any]) -> None:
        if self._publish_error:
            raise self._publish_error
        self.sent.append((name, args))

    def connection_for_write(self) -> FakeCeleryConnection:
        return self.connection


class DiskS3Client:
    """Stands in for a boto3 S3 client with a directory as the 'bucket', so upload and download really move files."""

    def __init__(self, bucket_root: Path) -> None:
        self._root = bucket_root

    def upload_file(self, filename: str, bucket: str, key: str) -> None:
        target = self._root / bucket / key
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(Path(filename).read_bytes())

    def download_file(self, bucket: str, key: str, filename: str) -> None:
        Path(filename).write_bytes((self._root / bucket / key).read_bytes())

    def list_objects_v2(self, Bucket: str, Prefix: str, MaxKeys: int | None = None) -> dict[str, Any]:
        base = self._root / Bucket
        keys = sorted(p.relative_to(base).as_posix() for p in base.rglob("*") if p.is_file()) if base.is_dir() else []
        matching = [{"Key": key} for key in keys if key.startswith(Prefix)]
        return {"Contents": matching[:MaxKeys]} if matching else {}

    def get_paginator(self, operation: str) -> "DiskS3Client":
        assert operation == "list_objects_v2"
        return self

    def paginate(self, Bucket: str, Prefix: str) -> list[dict[str, Any]]:
        return [self.list_objects_v2(Bucket, Prefix)]
