"""Strategy pattern — pluggable algorithms encapsulated as interchangeable objects.

Define a family of algorithms, encapsulate each one, and make them swappable.
The context (ItemSorter) delegates sorting to whichever strategy is configured,
without knowing or caring how it works.

Concrete strategies are plain functions that satisfy SortStrategy — no subclass
needed, just a matching signature.

Usage::

    sorter = ItemSorter(strategy=sort_by_name)
    sorted_items = sorter.sort(items)

    sorter.set_strategy(sort_by_id)
    sorted_items = sorter.sort(items)
"""
from collections.abc import Callable

from vlm_scene_description.models import Item

# A strategy is any callable that takes a list of items and returns a sorted list.
type SortStrategy = Callable[[list[Item]], list[Item]]


# ── Concrete strategies ─────────────────────────────────────────────────────

def sort_by_name(items: list[Item]) -> list[Item]:
    """Sort ascending by name (case-insensitive)."""
    return sorted(items, key=lambda i: i.name.casefold())


def sort_by_id(items: list[Item]) -> list[Item]:
    """Sort ascending by id."""
    return sorted(items, key=lambda i: i.id)


def sort_by_name_desc(items: list[Item]) -> list[Item]:
    """Sort descending by name (case-insensitive)."""
    return sorted(items, key=lambda i: i.name.casefold(), reverse=True)


# ── Context ─────────────────────────────────────────────────────────────────

class ItemSorter:
    """Context that delegates sorting to a pluggable SortStrategy.

    Swap the strategy at any time without changing the code that calls .sort().
    """

    def __init__(self, strategy: SortStrategy = sort_by_name) -> None:
        self._strategy = strategy

    def set_strategy(self, strategy: SortStrategy) -> None:
        """Replace the active strategy at runtime."""
        self._strategy = strategy

    def sort(self, items: list[Item]) -> list[Item]:
        """Apply the current strategy and return the sorted list."""
        return self._strategy(items)
