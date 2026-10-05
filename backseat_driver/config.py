import re
from enum import StrEnum
from functools import lru_cache
from typing import Literal, Self

from pydantic import Field, SecretStr, computed_field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class VlmBackend(StrEnum):
    HUGGINGFACE = "huggingface"
    OLLAMA = "ollama"
    ANTHROPIC = "anthropic"


class RunMode(StrEnum):
    MONOLITH = "monolith"  # jobs run on a thread inside the API process; no broker or database
    DISTRIBUTED = "distributed"  # jobs go through RabbitMQ to the ingest/caption workers, state in Postgres


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="BACKSEAT_DRIVER_",
        extra="ignore",
    )

    api_host: str = "127.0.0.1"
    api_port: int = 8080
    # Origins allowed to call the API from a browser; left empty, it is derived from the UI address below.
    cors_origins: list[str] = []
    log_format: Literal["colored", "json"] = "colored"

    # Model-comparison UI (`just ui`, `fastapi run backseat_driver/show/ui_server.py`)
    ui_host: str = "127.0.0.1"
    ui_port: int = 8081
    # Also show the API's completed jobs (re-read on every page load, newest per model), besides the result files.
    ui_all_jobs: bool = False
    # Where the browser reaches the API for the live-inference card, if not api_url (e.g. a port-forward).
    ui_public_api_url: str | None = None

    # nuScenes dataset: the dataroot is a cache, filled from nuscenes_url when <dataroot>/<version> is missing
    nuscenes_dataroot: str = "data/sets/nuscenes"
    nuscenes_version: str = "v1.0-mini"
    nuscenes_url: str = "https://d36yt3mvayqw5m.cloudfront.net/public/v1.0/v1.0-mini.tgz"
    camera_channel: str = "CAM_FRONT"

    # VLM captioning
    vlm_backend: VlmBackend = VlmBackend.HUGGINGFACE
    vlm_model_name: str | None = None
    ollama_model_name: str | None = None
    ollama_url: str = "http://localhost:11434"
    anthropic_model_name: str | None = None
    anthropic_api_key: SecretStr | None = None
    # Images `describe` captions together: one forward pass for HuggingFace, concurrent requests for Anthropic. 1 turns
    # batching off.
    caption_batch_size: int = Field(default=8, ge=1)

    # Where the monolith keeps its jobs (a SQLite file), so they survive a restart and the report UI can list them.
    # Distributed mode uses `database_url` instead.
    jobs_db_path: str = "output/jobs.db"

    # How the API runs `/jobs`. Monolith by default so local dev needs nothing else running; docker compose
    # sets `distributed`.
    mode: RunMode = RunMode.MONOLITH

    # Distributed mode only (API + queue workers)
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"
    database_url: str = "postgresql+psycopg://backseat_driver:backseat_driver@localhost:5432/backseat_driver"
    # Where the dataset lives for the distributed workers and API (S3-compatible; credentials via the AWS_* variables).
    # Required when `mode` is distributed (checked below) and unused by the monolith, hence no default. The endpoint is
    # only for S3-compatible stores that are not AWS.
    dataset_bucket: str | None = None
    s3_endpoint_url: str | None = None

    # Pipeline output: `describe` writes <output_dir>/<backend>__<model>.json unless told otherwise
    output_dir: str = "output"

    def model_name_for(self, backend: VlmBackend | None = None, model_name: str | None = None) -> str:
        """The model that `backend` (default: the configured one) runs; `model_name` overrides the configured one."""
        backend = backend or self.vlm_backend
        if model_name:
            return model_name
        if backend is VlmBackend.HUGGINGFACE:
            configured, variable = self.vlm_model_name, "BACKSEAT_DRIVER_VLM_MODEL_NAME"
        elif backend is VlmBackend.OLLAMA:
            configured, variable = self.ollama_model_name, "BACKSEAT_DRIVER_OLLAMA_MODEL_NAME"
        elif backend is VlmBackend.ANTHROPIC:
            configured, variable = self.anthropic_model_name, "BACKSEAT_DRIVER_ANTHROPIC_MODEL_NAME"
        else:
            raise ValueError(f"Unknown captioner backend {backend!r}")
        if not configured:
            raise ValueError(f"No model chosen for the {backend.value} backend: pass --model or set {variable}")
        return configured

    def output_path_for(self, backend: VlmBackend | None = None, model_name: str | None = None) -> str:
        """Default result file for a backend/model pair, so runs of different models never overwrite each other."""
        backend = backend or self.vlm_backend
        # Model names contain "/" and ":" (e.g. "Salesforce/blip-...", "llava:13b"), which are unsafe in filenames.
        slug = re.sub(r"[^A-Za-z0-9._-]+", "-", self.model_name_for(backend, model_name)).strip("-")
        return f"{self.output_dir}/{backend.value}__{slug}.json"

    @model_validator(mode="after")
    def _distributed_needs_a_dataset_bucket(self) -> Self:
        if self.mode is RunMode.DISTRIBUTED and not self.dataset_bucket:
            raise ValueError("BACKSEAT_DRIVER_DATASET_BUCKET must be set when BACKSEAT_DRIVER_MODE is distributed")
        return self

    @model_validator(mode="after")
    def _default_cors_origins(self) -> Self:
        if not self.cors_origins:
            hosts = dict.fromkeys(["127.0.0.1", "localhost", self.ui_host])
            self.cors_origins = [f"http://{host}:{self.ui_port}" for host in hosts]
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def api_url(self) -> str:
        return f"http://{self.api_host}:{self.api_port}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
