import re
from enum import StrEnum
from functools import lru_cache
from typing import Literal

from pydantic import SecretStr, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class VlmBackend(StrEnum):
    HUGGINGFACE = "huggingface"
    OLLAMA = "ollama"
    ANTHROPIC = "anthropic"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="BACKSEAT_DRIVER_",
        extra="ignore",
    )

    api_host: str = "127.0.0.1"
    api_port: int = 8080
    log_format: Literal["colored", "json"] = "colored"

    # Model-comparison UI (`backseat-driver ui`)
    ui_host: str = "127.0.0.1"
    ui_port: int = 8081

    # nuScenes dataset
    nuscenes_dataroot: str = "data/sets/nuscenes"
    nuscenes_version: str = "v1.0-mini"
    camera_channel: str = "CAM_FRONT"

    # VLM captioning
    vlm_backend: VlmBackend = VlmBackend.HUGGINGFACE
    vlm_model_name: str = "Salesforce/blip-image-captioning-base"
    ollama_model_name: str = "llava"
    ollama_url: str = "http://localhost:11434"
    anthropic_model_name: str = "claude-haiku-4-5-20251001"
    anthropic_api_key: SecretStr | None = None

    # Distributed mode (API + queue workers); unused by the batch CLI
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
            return self.vlm_model_name
        if backend is VlmBackend.OLLAMA:
            return self.ollama_model_name
        if backend is VlmBackend.ANTHROPIC:
            return self.anthropic_model_name
        raise ValueError(f"Unknown captioner backend {backend!r}")

    def output_path_for(self, backend: VlmBackend | None = None, model_name: str | None = None) -> str:
        """Default result file for a backend/model pair, so runs of different models never overwrite each other."""
        backend = backend or self.vlm_backend
        # Model names contain "/" and ":" (e.g. "Salesforce/blip-...", "llava:13b"), which are unsafe in filenames.
        slug = re.sub(r"[^A-Za-z0-9._-]+", "-", self.model_name_for(backend, model_name)).strip("-")
        return f"{self.output_dir}/{backend.value}__{slug}.json"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def api_url(self) -> str:
        return f"http://{self.api_host}:{self.api_port}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
