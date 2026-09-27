"""ItemRepository protocol — the storage contract for Item operations.

Any class that structurally implements these methods satisfies the protocol,
no explicit inheritance needed. This makes swapping implementations
(memory ↔ SQLite ↔ Postgres) seamless and keeps the service layer decoupled
from any particular database.
"""
from typing import Protocol

from vlm_scene_description.models import Item, ItemUpdate


class ItemRepository(Protocol):
    """Storage contract: CRUD operations + health check for Item entities."""

    async def healthcheck(self) -> bool: ...

    async def get_item(self, item_id: str) -> Item | None: ...

    async def list_items(self, offset: int = 0, limit: int = 20) -> tuple[list[Item], int]: ...

    async def create_item(self, item: Item) -> Item: ...

    async def update_item(self, item_id: str, patch: ItemUpdate) -> Item | None: ...

    async def delete_item(self, item_id: str) -> bool: ...
