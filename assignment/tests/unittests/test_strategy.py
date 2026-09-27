"""Tests for the Strategy pattern (bl/strategy.py)."""
from vlm_scene_description.bl.strategy import ItemSorter, sort_by_id, sort_by_name, sort_by_name_desc
from vlm_scene_description.models import Item


def _item(item_id: str, name: str) -> Item:
    return Item(id=item_id, name=name)


ITEMS = [
    _item("c", "Banana"),
    _item("a", "cherry"),
    _item("b", "apple"),
]


def test_sort_by_name_ascending() -> None:
    result = sort_by_name(ITEMS)
    assert [i.name for i in result] == ["apple", "Banana", "cherry"]


def test_sort_by_name_case_insensitive() -> None:
    items = [_item("1", "Zebra"), _item("2", "apple"), _item("3", "Mango")]
    result = sort_by_name(items)
    assert [i.name.lower() for i in result] == ["apple", "mango", "zebra"]


def test_sort_by_id() -> None:
    result = sort_by_id(ITEMS)
    assert [i.id for i in result] == ["a", "b", "c"]


def test_sort_by_name_desc() -> None:
    result = sort_by_name_desc(ITEMS)
    assert [i.name for i in result] == ["cherry", "Banana", "apple"]


def test_sorter_uses_default_strategy() -> None:
    sorter = ItemSorter()
    result = sorter.sort(ITEMS)
    assert result == sort_by_name(ITEMS)


def test_sorter_uses_injected_strategy() -> None:
    sorter = ItemSorter(strategy=sort_by_id)
    result = sorter.sort(ITEMS)
    assert [i.id for i in result] == ["a", "b", "c"]


def test_sorter_swaps_strategy_at_runtime() -> None:
    sorter = ItemSorter(strategy=sort_by_name)
    sorter.set_strategy(sort_by_id)
    result = sorter.sort(ITEMS)
    assert [i.id for i in result] == ["a", "b", "c"]


def test_sorter_does_not_mutate_input() -> None:
    original_order = [i.id for i in ITEMS]
    ItemSorter().sort(ITEMS)
    assert [i.id for i in ITEMS] == original_order


def test_strategy_can_be_a_lambda() -> None:
    reverse_id: ItemSorter = ItemSorter(strategy=lambda items: sorted(items, key=lambda i: i.id, reverse=True))
    result = reverse_id.sort(ITEMS)
    assert [i.id for i in result] == ["c", "b", "a"]


def test_empty_list_returns_empty() -> None:
    assert ItemSorter().sort([]) == []
