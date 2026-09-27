"""Pagination helpers for list endpoints."""
from pydantic import BaseModel, ConfigDict, Field


class PaginationParams(BaseModel):
    """Query parameter model for paginated list endpoints.

    Use as a dependency::

        @router.get("/items")
        async def list_items(
            pagination: Annotated[PaginationParams, Depends()],
        ) -> Page[Item]:
            items, total = await service.list_all(offset=pagination.offset, limit=pagination.page_size)
            return Page(items=items, total=total, page=pagination.page, page_size=pagination.page_size)

    ``extra="forbid"`` makes FastAPI reject unrecognized query parameters with 422.
    """

    model_config = ConfigDict(extra="forbid")

    page: int = Field(default=1, ge=1, description="Page number (1-indexed)")
    page_size: int = Field(default=20, ge=1, le=100, description="Items per page")

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size
