from functools import lru_cache
from typing import Literal

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="VLM_SCENE_DESCRIPTION_",
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
    vlm_model_name: str = "Salesforce/blip-image-captioning-base"

    # Distributed mode (API + queue workers); unused by the batch CLI
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"
    database_url: str = "postgresql://vlmscene:vlmscene@localhost:5432/vlmscene"

    # Pipeline output
    output_path: str = "output/scene_descriptions.json"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def api_url(self) -> str:
        return f"http://{self.api_host}:{self.api_port}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
