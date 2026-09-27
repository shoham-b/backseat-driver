"""Unit tests for ItemService — shows how to test domain services in isolation.

The service is constructed with a MemoryRepository and a fresh EventBus;
no HTTP layer involved.
"""
import pytest

from vlm_scene_description.bl.errors import ConflictError, NotFoundError
from vlm_scene_description.bl.events import EventBus, ItemCreated, ItemDeleted
from vlm_scene_description.bl.items import ItemService
from vlm_scene_description.db.memory import MemoryRepository
from vlm_scene_description.models import Item, ItemUpdate


@pytest.fixture
def service() -> ItemService:
    return ItemService(MemoryRepository(), EventBus())


async def test_create_then_retrieve(service: ItemService) -> None:
    item = Item(id="1", name="Widget", description="A test widget")
    created = await service.create(item)
    assert created.id == "1"
    fetched = await service.get("1")
    assert fetched.name == "Widget"


async def test_get_missing_raises_not_found(service: ItemService) -> None:
    with pytest.raises(NotFoundError):
        await service.get("missing")


async def test_create_duplicate_raises_conflict(service: ItemService) -> None:
    item = Item(id="dup", name="Dupe")
    await service.create(item)
    with pytest.raises(ConflictError):
        await service.create(item)


async def test_list_all_empty_initially(service: ItemService) -> None:
    items, total = await service.list_all()
    assert items == []
    assert total == 0


async def test_list_all_paginates(service: ItemService) -> None:
    for i in range(5):
        await service.create(Item(id=str(i), name=f"item-{i}"))
    page, total = await service.list_all(offset=2, limit=2)
    assert len(page) == 2
    assert total == 5


async def test_update_changes_only_supplied_fields(service: ItemService) -> None:
    await service.create(Item(id="upd", name="Original", description="Old desc"))
    updated = await service.update("upd", ItemUpdate(name="Updated"))
    assert updated.name == "Updated"
    assert updated.description == "Old desc"  # untouched
    assert updated.id == "upd"  # immutable


async def test_update_missing_item_raises_not_found(service: ItemService) -> None:
    with pytest.raises(NotFoundError):
        await service.update("ghost", ItemUpdate(name="X"))


async def test_delete_removes_item(service: ItemService) -> None:
    await service.create(Item(id="del", name="DeleteMe"))
    await service.delete("del")
    with pytest.raises(NotFoundError):
        await service.get("del")


async def test_delete_missing_item_raises_not_found(service: ItemService) -> None:
    with pytest.raises(NotFoundError):
        await service.delete("ghost")


async def test_create_emits_item_created_event() -> None:
    received: list[ItemCreated] = []

    async def handler(event: object) -> None:
        if isinstance(event, ItemCreated):
            received.append(event)

    bus = EventBus()
    bus.subscribe(ItemCreated, handler)  # type: ignore[arg-type]
    svc = ItemService(MemoryRepository(), bus)

    await svc.create(Item(id="e1", name="EventItem"))

    assert len(received) == 1
    assert received[0].item_id == "e1"


async def test_delete_emits_item_deleted_event() -> None:
    received: list[ItemDeleted] = []

    async def handler(event: object) -> None:
        if isinstance(event, ItemDeleted):
            received.append(event)

    bus = EventBus()
    bus.subscribe(ItemDeleted, handler)  # type: ignore[arg-type]
    svc = ItemService(MemoryRepository(), bus)

    await svc.create(Item(id="e2", name="ToDelete"))
    await svc.delete("e2")

    assert len(received) == 1
    assert received[0].item_id == "e2"
