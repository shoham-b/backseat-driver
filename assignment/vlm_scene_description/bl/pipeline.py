"""Chain of Responsibility — pass a request through a chain of handlers.

Each handler in the chain either handles the request itself, passes it on, or
rejects it entirely. Here the chain is a validation pipeline: each step checks
one rule about an Item and raises UnprocessableError if the rule fails.

Adding or reordering checks requires zero changes to callers — just edit the
pipeline definition.

Usage::

    pipeline = ValidationPipeline(
        NameNotEmptyValidator(),
        IdFormatValidator(),
        DescriptionLengthValidator(),
    )
    await pipeline.run(item)  # raises UnprocessableError on first failure
"""
from typing import Protocol

from vlm_scene_description.bl.errors import UnprocessableError
from vlm_scene_description.models import Item


class ItemValidator(Protocol):
    """A single validation step in the chain."""

    async def validate(self, item: Item) -> None:
        """Raise UnprocessableError if the item fails this check."""
        ...


# ── Concrete handlers ────────────────────────────────────────────────────────

class NameNotEmptyValidator:
    """Reject items whose name is blank or whitespace-only."""

    async def validate(self, item: Item) -> None:
        if not item.name.strip():
            raise UnprocessableError("name must not be blank")


class IdFormatValidator:
    """Reject ids that contain characters other than letters, digits, hyphens, underscores."""

    async def validate(self, item: Item) -> None:
        clean = item.id.replace("-", "").replace("_", "")
        if not clean.isalnum():
            raise UnprocessableError(
                f"id {item.id!r}: only letters, digits, hyphens, and underscores allowed"
            )


class DescriptionLengthValidator:
    """Reject items whose description exceeds a configurable maximum length."""

    def __init__(self, max_length: int = 500) -> None:
        self._max = max_length

    async def validate(self, item: Item) -> None:
        if item.description and len(item.description) > self._max:
            raise UnprocessableError(
                f"description is {len(item.description)} characters — maximum is {self._max}"
            )


# ── Chain ────────────────────────────────────────────────────────────────────

class ValidationPipeline:
    """Runs validators in registration order; stops at the first failure.

    This is the Chain of Responsibility: each handler either passes the item
    along or raises, terminating the chain.
    """

    def __init__(self, *validators: ItemValidator) -> None:
        self._validators = validators

    async def run(self, item: Item) -> None:
        """Validate item through the full chain. Raises UnprocessableError on failure."""
        for validator in self._validators:
            await validator.validate(item)
