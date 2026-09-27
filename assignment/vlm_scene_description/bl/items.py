"""Example service — demonstrates constructor DI, Repository delegation, and domain events.

Replace with your own domain logic. The service receives an ItemRepository
via __init__ so any implementation (memory, SQLite, a test double) can be
injected without changing this class.
"""
from vlm_scene_description.bl.errors import ConflictError, NotFoundError
from vlm_scene_description.bl.events import EventBus, ItemCreated, ItemDeleted
from vlm_scene_description.db.item_repository import ItemRepository
from vlm_scene_description.models import Item, ItemUpdate


class ItemService:
    def __init__(self, repo: ItemRepository, bus: EventBus) -> None:
        self._repo = repo
        self._bus = bus

    async def get(self, item_id: str) -> Item:
        item = await self._repo.get_item(item_id)
        if item is None:
            raise NotFoundError(f"item {item_id!r} not found")
        return item

    async def list_all(self, offset: int = 0, limit: int = 20) -> tuple[list[Item], int]:
        return await self._repo.list_items(offset=offset, limit=limit)

    async def create(self, item: Item) -> Item:
        if await self._repo.get_item(item.id) is not None:
            raise ConflictError(f"item {item.id!r} already exists")
        created = await self._repo.create_item(item)
        await self._bus.emit(ItemCreated(item_id=created.id, name=created.name))
        return created

    async def update(self, item_id: str, patch: ItemUpdate) -> Item:
        updated = await self._repo.update_item(item_id, patch)
        if updated is None:
            raise NotFoundError(f"item {item_id!r} not found")
        return updated

    async def delete(self, item_id: str) -> None:
        deleted = await self._repo.delete_item(item_id)
        if not deleted:
            raise NotFoundError(f"item {item_id!r} not found")
        await self._bus.emit(ItemDeleted(item_id=item_id))

