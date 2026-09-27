from vlm_scene_description.db.base import Repository
from vlm_scene_description.models import Item, ItemUpdate


class MemoryRepository(Repository):
    """In-memory repository — zero dependencies, instant, safe for tests and local dev.

    Structurally satisfies ItemRepository (duck-typed via Protocol) without
    requiring explicit inheritance from it.
    """

    def __init__(self) -> None:
        self._items: dict[str, Item] = {}

    async def healthcheck(self) -> bool:
        return True

    async def get_item(self, item_id: str) -> Item | None:
        return self._items.get(item_id)

    async def list_items(self, offset: int = 0, limit: int = 20) -> tuple[list[Item], int]:
        items = list(self._items.values())
        return items[offset : offset + limit], len(items)

    async def create_item(self, item: Item) -> Item:
        self._items[item.id] = item
        return item

    async def update_item(self, item_id: str, patch: ItemUpdate) -> Item | None:
        item = self._items.get(item_id)
        if item is None:
            return None
        self._items[item_id] = item.model_copy(update=patch.model_dump(exclude_unset=True))
        return self._items[item_id]

    async def delete_item(self, item_id: str) -> bool:
        return self._items.pop(item_id, None) is not None

    def clear(self) -> None:
        """Remove all stored items. Call in test fixtures to isolate state."""
        self._items.clear()
