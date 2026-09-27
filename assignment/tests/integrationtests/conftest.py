from collections.abc import AsyncGenerator, Iterator

import httpx
import pytest
from fastapi.testclient import TestClient

from vlm_scene_description.api.app import app
from vlm_scene_description.api.dependencies import get_repository
from vlm_scene_description.db.memory import MemoryRepository




@pytest.fixture(scope="session")
def client() -> Iterator[TestClient]:
    app.dependency_overrides[get_repository] = lambda: MemoryRepository()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(get_repository, None)


@pytest.fixture(scope="session")
async def async_client() -> AsyncGenerator[httpx.AsyncClient]:
    app.dependency_overrides[get_repository] = lambda: MemoryRepository()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.pop(get_repository, None)
