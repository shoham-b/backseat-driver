"""Unit tests for ItemBuilder."""
import pytest

from vlm_scene_description.bl.builder import ItemBuilder


def test_build_with_all_fields() -> None:
    item = ItemBuilder("b-1").name("Widget").description("A widget").build()
    assert item.id == "b-1"
    assert item.name == "Widget"
    assert item.description == "A widget"


def test_build_without_description() -> None:
    item = ItemBuilder("b-2").name("Minimal").build()
    assert item.id == "b-2"
    assert item.description is None


def test_build_without_name_raises() -> None:
    with pytest.raises(ValueError, match="name is required"):
        ItemBuilder("b-3").build()


def test_builder_is_fluent() -> None:
    builder = ItemBuilder("b-4")
    assert builder.name("A").description("B") is builder


def test_builder_produces_independent_items() -> None:
    builder = ItemBuilder("b-5").name("Original")
    item1 = builder.build()
    builder.name("Modified")
    item2 = builder.build()
    assert item1.name == "Original"
    assert item2.name == "Modified"
