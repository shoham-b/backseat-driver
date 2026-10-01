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
    database_url: str = "postgresql://backseat_driver:backseat_driver@localhost:5432/backseat_driver"

    # Pipeline output
    output_path: str = "output/scene_descriptions.json"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def api_url(self) -> str:
        return f"http://{self.api_host}:{self.api_port}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
