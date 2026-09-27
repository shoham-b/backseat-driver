"""Command pattern — encapsulate operations as objects with undo support.

Turning requests into Command objects lets you:
- Queue or schedule operations for later execution
- Log every mutation that has happened
- Undo the last N operations in LIFO order

Each command stores the data it needs to both *do* and *undo* the operation,
so callers only interact with execute/undo — they never touch the repository.

Usage::

    history = CommandHistory()

    cmd = CreateItemCommand(repo=repo, item=item)
    await history.execute(cmd)   # creates item

    await history.undo_last()    # deletes it again
"""
from dataclasses import dataclass, field
from typing import Protocol

from vlm_scene_description.bl.errors import NotFoundError
from vlm_scene_description.db.item_repository import ItemRepository
from vlm_scene_description.models import Item


class Command(Protocol):
    """A reversible, executable operation."""

    async def execute(self) -> None: ...

    async def undo(self) -> None: ...


# ── Concrete commands ────────────────────────────────────────────────────────

@dataclass
class CreateItemCommand:
    """Creates an item; undo deletes it."""

    repo: ItemRepository
    item: Item

    async def execute(self) -> None:
        await self.repo.create_item(self.item)

    async def undo(self) -> None:
        await self.repo.delete_item(self.item.id)


@dataclass
class DeleteItemCommand:
    """Deletes an item after fetching it for undo; undo recreates it."""

    repo: ItemRepository
    item_id: str
    _snapshot: Item | None = field(default=None, init=False, repr=False)

    async def execute(self) -> None:
        self._snapshot = await self.repo.get_item(self.item_id)
        if self._snapshot is None:
            raise NotFoundError(f"item {self.item_id!r} not found")
        await self.repo.delete_item(self.item_id)

    async def undo(self) -> None:
        if self._snapshot is not None:
            await self.repo.create_item(self._snapshot)


# ── Invoker ──────────────────────────────────────────────────────────────────

class CommandHistory:
    """Invoker that executes commands and maintains an undo stack.

    Keeps every executed command in a LIFO stack so undo_last() can reverse
    the most recent mutation at any time.
    """

    def __init__(self) -> None:
        self._stack: list[Command] = []

    async def execute(self, command: Command) -> None:
        """Execute the command and push it onto the undo stack."""
        await command.execute()
        self._stack.append(command)

    async def undo_last(self) -> bool:
        """Undo the most recently executed command.

        Returns True if a command was undone, False if the stack was empty.
        """
        if not self._stack:
            return False
        await self._stack.pop().undo()
        return True

    @property
    def depth(self) -> int:
        """Number of commands available to undo."""
        return len(self._stack)
