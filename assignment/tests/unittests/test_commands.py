"""Tests for the Command pattern with undo support (bl/commands.py)."""
import pytest

from vlm_scene_description.bl.commands import CommandHistory, CreateItemCommand, DeleteItemCommand
from vlm_scene_description.bl.errors import NotFoundError
from vlm_scene_description.db.memory import MemoryRepository
from vlm_scene_description.models import Item


@pytest.fixture
def repo() -> MemoryRepository:
    return MemoryRepository()


def _item(item_id: str = "item-1", name: str = "Widget") -> Item:
    return Item(id=item_id, name=name)


# ── CreateItemCommand ────────────────────────────────────────────────────────

async def test_create_command_stores_item(repo: MemoryRepository) -> None:
    cmd = CreateItemCommand(repo=repo, item=_item())
    await cmd.execute()
    assert await repo.get_item("item-1") is not None


async def test_create_command_undo_deletes_item(repo: MemoryRepository) -> None:
    cmd = CreateItemCommand(repo=repo, item=_item())
    await cmd.execute()
    await cmd.undo()
    assert await repo.get_item("item-1") is None


# ── DeleteItemCommand ────────────────────────────────────────────────────────

async def test_delete_command_removes_item(repo: MemoryRepository) -> None:
    await repo.create_item(_item())
    cmd = DeleteItemCommand(repo=repo, item_id="item-1")
    await cmd.execute()
    assert await repo.get_item("item-1") is None


async def test_delete_command_undo_restores_item(repo: MemoryRepository) -> None:
    original = _item()
    await repo.create_item(original)
    cmd = DeleteItemCommand(repo=repo, item_id="item-1")
    await cmd.execute()
    await cmd.undo()
    restored = await repo.get_item("item-1")
    assert restored is not None
    assert restored.name == original.name


async def test_delete_command_raises_on_missing_item(repo: MemoryRepository) -> None:
    cmd = DeleteItemCommand(repo=repo, item_id="nonexistent")
    with pytest.raises(NotFoundError):
        await cmd.execute()


# ── CommandHistory ───────────────────────────────────────────────────────────

async def test_history_execute_and_undo(repo: MemoryRepository) -> None:
    history = CommandHistory()
    await history.execute(CreateItemCommand(repo=repo, item=_item()))
    assert await repo.get_item("item-1") is not None

    undone = await history.undo_last()
    assert undone is True
    assert await repo.get_item("item-1") is None


async def test_history_undo_empty_returns_false(repo: MemoryRepository) -> None:
    history = CommandHistory()
    assert await history.undo_last() is False


async def test_history_depth_tracks_stack(repo: MemoryRepository) -> None:
    history = CommandHistory()
    assert history.depth == 0

    await history.execute(CreateItemCommand(repo=repo, item=_item("a")))
    await history.execute(CreateItemCommand(repo=repo, item=_item("b")))
    assert history.depth == 2

    await history.undo_last()
    assert history.depth == 1


async def test_history_undo_lifo_order(repo: MemoryRepository) -> None:
    history = CommandHistory()
    await history.execute(CreateItemCommand(repo=repo, item=_item("a")))
    await history.execute(CreateItemCommand(repo=repo, item=_item("b")))

    await history.undo_last()
    assert await repo.get_item("b") is None
    assert await repo.get_item("a") is not None

    await history.undo_last()
    assert await repo.get_item("a") is None


async def test_history_multiple_commands_full_roundtrip(repo: MemoryRepository) -> None:
    history = CommandHistory()
    items = [_item(f"item-{i}", f"Name {i}") for i in range(3)]
    for item in items:
        await history.execute(CreateItemCommand(repo=repo, item=item))

    for _ in items:
        await history.undo_last()

    for item in items:
        assert await repo.get_item(item.id) is None
