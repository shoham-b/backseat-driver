import re
from enum import StrEnum
from functools import lru_cache
from typing import Literal, Self

from pydantic import SecretStr, computed_field, model_validator
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

    # Model-comparison UI (`backseat-driver ui`)
    ui_host: str = "127.0.0.1"
    ui_port: int = 8081

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

    # How the API runs `/jobs`. Monolith by default so local dev needs nothing else running; docker compose
    # sets `distributed`.
    mode: RunMode = RunMode.MONOLITH

    # Distributed mode only (API + queue workers)
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"
    database_url: str = "postgresql+psycopg://backseat_driver:backseat_driver@localhost:5432/backseat_driver"

    # Pipeline output: `run` writes <output_dir>/<backend>__<model>.json unless told otherwise
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
