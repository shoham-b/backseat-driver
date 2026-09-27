"""Outbound HTTP client pattern for the business-logic layer.

Copy and adapt — replace the URL, response model, and error handling
to match your external service. Requires httpx and stamina in the api dependency group.
"""
import httpx
import stamina


# Retry on transient network errors (timeouts, connection resets).
# HTTPStatusError (4xx/5xx) is NOT retried — those are deterministic.
@stamina.retry(on=httpx.TransportError, attempts=3, wait_initial=0.5, wait_max=10.0)
async def get_json(url: str) -> object:
    """GET a JSON endpoint with automatic retry on network errors."""
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        response.raise_for_status()
        data: object = response.json()
        return data
