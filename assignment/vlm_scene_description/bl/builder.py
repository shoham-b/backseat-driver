"""Builder pattern — construct complex objects step by step.

Useful when an object has many optional fields or requires validation at
construction time. Chain setter calls then call .build() to get the immutable
result. Raises ValueError early if required fields are missing.

Usage::

    item = ItemBuilder("my-id").name("My Item").description("Optional").build()
"""
from vlm_scene_description.models import Item


class ItemBuilder:
    """Fluent builder for Item.

    Chain .name() and .description() calls, then call .build() to produce an
    immutable Item. Raises ValueError if required fields have not been set.
    """

    def __init__(self, item_id: str) -> None:
        self._id = item_id
        self._name: str | None = None
        self._description: str | None = None

    def name(self, name: str) -> "ItemBuilder":
        self._name = name
        return self

    def description(self, description: str) -> "ItemBuilder":
        self._description = description
        return self

    def build(self) -> Item:
        if self._name is None:
            raise ValueError("name is required — call .name() before .build()")
        return Item(id=self._id, name=self._name, description=self._description)
