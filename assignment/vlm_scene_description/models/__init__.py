"""Domain models — pure Pydantic, no imports from api/, bl/, or db/."""

from pydantic import BaseModel


class Item(BaseModel):
    """Example domain entity — replace with your own types."""

    id: str
    name: str
    description: str | None = None


class ItemUpdate(BaseModel):
    """Partial-update payload for Item — all fields are optional.

    Only fields present in the request body are applied; absent fields leave
    the existing value unchanged. Use with Repository.update_item() and the
    PATCH endpoint.
    """

    name: str | None = None
    description: str | None = None


class Page[T](BaseModel):
    """Generic paginated response envelope.

    Usage::

        @router.get("/items")
        async def list_items(...) -> Page[Item]:
            rows, total = await service.list_all(offset=p.offset, limit=p.page_size)
            return Page(items=rows, total=total, page=p.page, page_size=p.page_size)
    """

    items: list[T]
    total: int
    page: int
    page_size: int

