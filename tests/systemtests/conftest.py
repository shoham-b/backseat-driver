from collections.abc import AsyncGenerator

import httpx
import pytest


@pytest.fixture(scope="session")
async def api_client(api_url: str) -> AsyncGenerator[httpx.AsyncClient]:
    async with httpx.AsyncClient(base_url=api_url, timeout=10.0) as client:
        try:
            response = await client.get("/ready")
            response.raise_for_status()
        except Exception as exc:
            pytest.fail(f"Service at {api_url} is not reachable — run `just infra` + `just dev`, or `just up`: {exc}")
        yield client
