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





    @computed_field  # type: ignore[prop-decorator]
    @property
    def api_url(self) -> str:
        return f"http://{self.api_host}:{self.api_port}"



@lru_cache
def get_settings() -> Settings:
    return Settings()
