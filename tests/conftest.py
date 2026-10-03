import os

import pytest

from backseat_driver.config import Settings

# The API has no default model and builds its captioner at startup, so the tests that boot the real app need one set
# (the captioner is overridden by a fake, so this never loads a model).
os.environ.setdefault("BACKSEAT_DRIVER_VLM_MODEL_NAME", "fake-model")


@pytest.fixture(scope="session")
def settings() -> Settings:
    return Settings()


@pytest.fixture(scope="session")
def api_url() -> str:
    """Target of the smoke/system tests; `backseat-driver test smoke --api-url` exports it as API_URL."""
    return os.environ.get("API_URL", "http://localhost:8080")
