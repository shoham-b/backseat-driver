from collections.abc import Callable, Iterator
from contextlib import contextmanager
from http import HTTPStatus
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from vlm_scene_description.api.app import app
from vlm_scene_description.api.dependencies import get_repository
from vlm_scene_description.db.base import Repository
from vlm_scene_description.db.memory import MemoryRepository


class _UnhealthyRepository(Repository):
    async def healthcheck(self) -> bool:
        return False


@contextmanager
def _override_repository(factory: Callable[[], Repository]) -> Iterator[None]:
    original = app.dependency_overrides.get(get_repository)
    app.dependency_overrides[get_repository] = factory
    try:
        yield
    finally:
        if original is None:
            app.dependency_overrides.pop(get_repository, None)
        else:
            app.dependency_overrides[get_repository] = original


def test_liveness(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == HTTPStatus.OK
    assert response.json() == {"status": "ok"}


def test_request_id_generated_when_absent(client: TestClient) -> None:
    response = client.get("/health")

    assert "x-request-id" in response.headers


def test_request_id_propagated_from_request(client: TestClient) -> None:
    response = client.get("/health", headers={"X-Request-ID": "my-trace-id"})

    assert response.headers["x-request-id"] == "my-trace-id"


def test_readiness_healthy(client: TestClient) -> None:
    response = client.get("/ready")

    assert response.status_code == HTTPStatus.OK
    assert response.json() == {"status": "ok"}


def test_readiness_unhealthy_backend() -> None:
    with _override_repository(lambda: _UnhealthyRepository()):
        response = TestClient(app).get("/ready")

    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    error = response.json()["error"]
    assert error["code"] == HTTPStatus.SERVICE_UNAVAILABLE
    assert error["status"] == HTTPStatus.SERVICE_UNAVAILABLE.phrase
    assert "message" in error


def test_get_repository_reads_from_app_state() -> None:
    mock_request = MagicMock()
    mock_request.app.state.repository = MemoryRepository()

    result = get_repository(mock_request)

    assert isinstance(result, MemoryRepository)


def test_error_response_shape_on_unhandled_exception() -> None:
    def _raise() -> Repository:
        raise RuntimeError("boom")

    with _override_repository(_raise):
        response = TestClient(app, raise_server_exceptions=False).get("/ready")

    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    error = response.json()["error"]
    assert error["code"] == HTTPStatus.INTERNAL_SERVER_ERROR
    assert error["status"] == HTTPStatus.INTERNAL_SERVER_ERROR.phrase
    assert "message" in error
