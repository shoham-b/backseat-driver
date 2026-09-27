"""Example resource router — pagination, DI, domain errors, partial update, delete.

Domain errors raised in the service layer are automatically translated to HTTP
4xx responses by domain_error_handler in exception_handlers.py — no try/except
needed here. Also demonstrates BackgroundTasks for fire-and-forget work.

Streaming patterns:
- GET /items/stream  — NDJSON: one JSON object per line, no envelope, memory-efficient
- GET /items/sse     — Server-Sent Events: real-time push whenever an item is created/deleted

Delete or adapt this file when building your own routes.
"""
import asyncio
import json
from collections.abc import AsyncGenerator
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import StreamingResponse
from loguru import logger

from vlm_scene_description.api.pagination import PaginationParams
from vlm_scene_description.bl.events import DomainEvent, ItemCreated, ItemDeleted
from vlm_scene_description.bl.items import ItemService
from vlm_scene_description.models import Item, ItemUpdate, Page

router = APIRouter(prefix="/items", tags=["items"])

_404: dict[int | str, dict[str, Any]] = {404: {"description": "Item not found"}}
_409: dict[int | str, dict[str, Any]] = {409: {"description": "Item already exists"}}


def get_item_service(request: Request) -> ItemService:
    return ItemService(
        repo=request.app.state.repository,  # type: ignore[arg-type]
        bus=request.app.state.event_bus,
    )


@router.get("/")
async def list_items(
    pagination: Annotated[PaginationParams, Depends()],
    service: Annotated[ItemService, Depends(get_item_service)],
) -> Page[Item]:
    """List items with offset pagination."""
    items, total = await service.list_all(
        offset=pagination.offset, limit=pagination.page_size
    )
    return Page(items=items, total=total, page=pagination.page, page_size=pagination.page_size)


@router.get("/stream", response_class=StreamingResponse)
async def stream_items(
    service: Annotated[ItemService, Depends(get_item_service)],
) -> StreamingResponse:
    """Stream all items as NDJSON (application/x-ndjson).

    Each line is a complete JSON object — clients can parse line-by-line without
    waiting for the full response. Useful for large exports that would otherwise
    require buffering the entire result set in memory.

    Example (curl)::

        curl -N http://localhost:8000/items/stream
    """

    async def generate() -> AsyncGenerator[bytes]:
        offset = 0
        page_size = 100
        while True:
            items, _ = await service.list_all(offset=offset, limit=page_size)
            for item in items:
                yield item.model_dump_json().encode() + b"\n"
            if len(items) < page_size:
                break
            offset += page_size

    return StreamingResponse(generate(), media_type="application/x-ndjson")


@router.get("/sse")
async def sse_events(request: Request) -> StreamingResponse:
    """Stream item domain events as Server-Sent Events (text/event-stream).

    The client receives a push notification each time an item is created or
    deleted — no polling required. The connection stays open until the client
    disconnects.

    Each event has the form::

        event: ItemCreated
        data: {"item_id": "x", "name": "Widget"}

    Example (curl)::

        curl -N -H "Accept: text/event-stream" http://localhost:8000/items/sse
    """
    bus = request.app.state.event_bus
    queue: asyncio.Queue[str] = asyncio.Queue()

    async def _enqueue(event: DomainEvent) -> None:
        name = type(event).__name__
        payload = json.dumps(event.__dict__)
        await queue.put(f"event: {name}\ndata: {payload}\n\n")

    bus.subscribe(ItemCreated, _enqueue)
    bus.subscribe(ItemDeleted, _enqueue)

    async def generate() -> AsyncGenerator[str]:
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    chunk = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield chunk
                except TimeoutError:
                    yield ": keepalive\n\n"  # SSE comment — prevents proxy timeouts
        finally:
            bus.unsubscribe(ItemCreated, _enqueue)
            bus.unsubscribe(ItemDeleted, _enqueue)

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.get("/{item_id}", responses=_404)
async def get_item(
    item_id: str,
    service: Annotated[ItemService, Depends(get_item_service)],
) -> Item:
    """Fetch a single item by id. Raises 404 if it does not exist."""
    return await service.get(item_id)


@router.post("/", status_code=201, responses=_409)
async def create_item(
    item: Item,
    service: Annotated[ItemService, Depends(get_item_service)],
    background_tasks: BackgroundTasks,
) -> Item:
    """Create an item. Raises 409 if an item with the same id already exists.

    Demonstrates BackgroundTasks: _audit_created runs after the response is
    sent, without blocking the client.
    """
    created = await service.create(item)
    background_tasks.add_task(_audit_created, created.id)
    return created


@router.patch("/{item_id}", responses=_404)
async def update_item(
    item_id: str,
    patch: ItemUpdate,
    service: Annotated[ItemService, Depends(get_item_service)],
) -> Item:
    """Partially update an item. Only fields present in the body are changed."""
    return await service.update(item_id, patch)


@router.delete("/{item_id}", status_code=204, responses=_404)
async def delete_item(
    item_id: str,
    service: Annotated[ItemService, Depends(get_item_service)],
) -> None:
    """Delete an item. Raises 404 if it does not exist."""
    await service.delete(item_id)


async def _audit_created(item_id: str) -> None:
    """Background task — executes after the response has been sent to the client."""
    logger.debug("audit: item created", item_id=item_id)
