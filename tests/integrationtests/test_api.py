from collections.abc import Callable, Iterator
from contextlib import contextmanager
from http import HTTPStatus
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from tests.fakes import FakeJobQueue, FakeJobStore
from vlmscene.api.app import app
from vlmscene.api.dependencies import get_captioner, get_job_queue, get_job_store
from vlmscene.bl.captioner import BlipCaptioner, Captioner


class _UnhealthyCaptioner(BlipCaptioner):
    def healthcheck(self) -> bool:
        return False


@contextmanager
def _override_captioner(factory: Callable[[], Captioner]) -> Iterator[None]:
    original = app.dependency_overrides.get(get_captioner)
    app.dependency_overrides[get_captioner] = factory
    try:
        yield
    finally:
        if original is None:
            app.dependency_overrides.pop(get_captioner, None)
        else:
            app.dependency_overrides[get_captioner] = original


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
    with _override_captioner(lambda: _UnhealthyCaptioner()):
        response = TestClient(app).get("/ready")

    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    error = response.json()["error"]
    assert error["code"] == HTTPStatus.SERVICE_UNAVAILABLE
    assert error["status"] == HTTPStatus.SERVICE_UNAVAILABLE.phrase
    assert "message" in error


def test_get_captioner_reads_from_app_state() -> None:
    mock_request = MagicMock()
    mock_request.app.state.captioner = BlipCaptioner()

    result = get_captioner(mock_request)

    assert isinstance(result, BlipCaptioner)


def test_error_response_shape_on_unhandled_exception() -> None:
    def _raise() -> Captioner:
        raise RuntimeError("boom")

    with _override_captioner(_raise):
        response = TestClient(app, raise_server_exceptions=False).get("/ready")

    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    error = response.json()["error"]
    assert error["code"] == HTTPStatus.INTERNAL_SERVER_ERROR
    assert error["status"] == HTTPStatus.INTERNAL_SERVER_ERROR.phrase
    assert "message" in error


def test_describe_returns_caption(client: TestClient) -> None:
    from io import BytesIO

    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", (4, 4), color="blue").save(buf, format="PNG")
    buf.seek(0)

    response = client.post("/describe", files={"image": ("scene.png", buf, "image/png")})

    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert body["description"] == "a fake scene description"
    assert body["model_name"] == "fake-model"


def test_describe_rejects_empty_file(client: TestClient) -> None:
    response = client.post("/describe", files={"image": ("empty.png", b"", "image/png")})

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


@pytest.mark.parametrize(
    ("dependency", "unhealthy"),
    [(get_job_queue, FakeJobQueue(healthy=False)), (get_job_store, FakeJobStore(healthy=False))],
)
def test_readiness_unhealthy_queue_or_store(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, dependency: Callable[..., object], unhealthy: object
) -> None:
    monkeypatch.setitem(app.dependency_overrides, dependency, lambda: unhealthy)

    response = client.get("/ready")

    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
