from collections.abc import Iterator

import httpx
import pytest


@pytest.fixture(scope="session")
def smoke_client(api_url: str) -> Iterator[httpx.Client]:
    """HTTP client pointed at a running instance. Fails (not skips) if unreachable."""
    with httpx.Client(base_url=api_url, timeout=5.0) as client:
        try:
            client.get("/health").raise_for_status()
        except Exception as exc:
            pytest.fail(f"Service at {api_url} is not reachable: {exc}")
        yield client
