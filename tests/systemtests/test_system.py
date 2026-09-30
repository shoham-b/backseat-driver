from http import HTTPStatus

import httpx


async def test_liveness(api_client: httpx.AsyncClient) -> None:
    response = await api_client.get("/health")

    assert response.status_code == HTTPStatus.OK
    assert response.json()["status"] == "ok"


async def test_readiness(api_client: httpx.AsyncClient) -> None:
    response = await api_client.get("/ready")

    assert response.status_code == HTTPStatus.OK
    assert response.json()["status"] == "ok"
