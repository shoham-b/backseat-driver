"""Shows how to use respx to mock outbound HTTP calls from the bl layer."""
import httpx
import pytest
import respx

from vlm_scene_description.bl.http_client import get_json


@respx.mock
async def test_get_json_success() -> None:
    respx.get("https://api.example.com/data").mock(
        return_value=httpx.Response(200, json={"key": "value"})
    )

    result = await get_json("https://api.example.com/data")

    assert result == {"key": "value"}


@respx.mock
async def test_get_json_raises_on_error_status() -> None:
    respx.get("https://api.example.com/data").mock(
        return_value=httpx.Response(503)
    )

    with pytest.raises(httpx.HTTPStatusError):
        await get_json("https://api.example.com/data")
