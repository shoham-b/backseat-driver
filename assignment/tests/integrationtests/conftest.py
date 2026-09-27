from collections.abc import AsyncGenerator, Iterator

import httpx
import pytest
from fastapi.testclient import TestClient

from vlm_scene_description.api.app import app
from vlm_scene_description.api.dependencies import get_captioner
from vlm_scene_description.bl.captioner import Captioner


class FakeCaptioner(Captioner):
    """Stub captioner — returns a canned caption instantly, no model download."""

    model_name = "fake-model"

    def caption(self, image_path: str) -> str:
        return "a fake scene description"

    def healthcheck(self) -> bool:
        return True


@pytest.fixture(scope="session")
def client() -> Iterator[TestClient]:
    app.dependency_overrides[get_captioner] = lambda: FakeCaptioner()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(get_captioner, None)


@pytest.fixture(scope="session")
async def async_client() -> AsyncGenerator[httpx.AsyncClient]:
    app.dependency_overrides[get_captioner] = lambda: FakeCaptioner()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.pop(get_captioner, None)
