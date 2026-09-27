"""Decorator pattern — adds structured logging to any ItemRepository.

LoggingRepository wraps any object that satisfies the ItemRepository protocol
and transparently adds a log call around every operation. The wrapped object
doesn't know it's being decorated; callers don't know logging is happening.

Usage::

    repo = LoggingRepository(MemoryRepository())
    await repo.create_item(item)  # logs the call automatically
"""
from loguru import logger

from vlm_scene_description.db.item_repository import ItemRepository
from vlm_scene_description.models import Item, ItemUpdate


class LoggingRepository:
    """Decorator that wraps an ItemRepository and logs every call."""

    def __init__(self, repo: ItemRepository) -> None:
        self._repo = repo

    async def healthcheck(self) -> bool:
        result = await self._repo.healthcheck()
        logger.debug("healthcheck", result=result)
        return result

    async def get_item(self, item_id: str) -> Item | None:
        result = await self._repo.get_item(item_id)
        logger.debug("get_item", item_id=item_id, found=result is not None)
        return result

    async def list_items(self, offset: int = 0, limit: int = 20) -> tuple[list[Item], int]:
        items, total = await self._repo.list_items(offset=offset, limit=limit)
        logger.debug("list_items", offset=offset, limit=limit, returned=len(items), total=total)
        return items, total

    async def create_item(self, item: Item) -> Item:
        result = await self._repo.create_item(item)
        logger.debug("create_item", item_id=result.id)
        return result

    async def update_item(self, item_id: str, patch: ItemUpdate) -> Item | None:
        result = await self._repo.update_item(item_id, patch)
        logger.debug("update_item", item_id=item_id, found=result is not None)
        return result

    async def delete_item(self, item_id: str) -> bool:
        result = await self._repo.delete_item(item_id)
        logger.debug("delete_item", item_id=item_id, deleted=result)
        return result
