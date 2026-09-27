"""Tests for the Chain of Responsibility validation pipeline (bl/pipeline.py)."""
import pytest

from vlm_scene_description.bl.errors import UnprocessableError
from vlm_scene_description.bl.pipeline import (
    DescriptionLengthValidator,
    IdFormatValidator,
    NameNotEmptyValidator,
    ValidationPipeline,
)
from vlm_scene_description.models import Item


def _item(item_id: str = "abc", name: str = "Valid Name", description: str | None = None) -> Item:
    return Item(id=item_id, name=name, description=description)


# ── NameNotEmptyValidator ────────────────────────────────────────────────────

async def test_name_not_empty_passes_normal_name() -> None:
    await NameNotEmptyValidator().validate(_item(name="Widget"))


async def test_name_not_empty_rejects_blank() -> None:
    with pytest.raises(UnprocessableError, match="blank"):
        await NameNotEmptyValidator().validate(_item(name="   "))


async def test_name_not_empty_rejects_empty_string() -> None:
    with pytest.raises(UnprocessableError):
        await NameNotEmptyValidator().validate(_item(name=""))


# ── IdFormatValidator ────────────────────────────────────────────────────────

async def test_id_format_passes_alphanumeric() -> None:
    await IdFormatValidator().validate(_item(item_id="abc123"))


async def test_id_format_passes_hyphens_and_underscores() -> None:
    await IdFormatValidator().validate(_item(item_id="my-item_v2"))


async def test_id_format_rejects_special_chars() -> None:
    with pytest.raises(UnprocessableError, match="only letters"):
        await IdFormatValidator().validate(_item(item_id="bad id!"))


async def test_id_format_rejects_spaces() -> None:
    with pytest.raises(UnprocessableError):
        await IdFormatValidator().validate(_item(item_id="has space"))


# ── DescriptionLengthValidator ───────────────────────────────────────────────

async def test_description_length_passes_within_limit() -> None:
    await DescriptionLengthValidator(max_length=10).validate(_item(description="short"))


async def test_description_length_passes_none() -> None:
    await DescriptionLengthValidator().validate(_item(description=None))


async def test_description_length_rejects_too_long() -> None:
    with pytest.raises(UnprocessableError, match="maximum"):
        await DescriptionLengthValidator(max_length=5).validate(_item(description="too long string"))


async def test_description_length_default_500() -> None:
    await DescriptionLengthValidator().validate(_item(description="x" * 500))
    with pytest.raises(UnprocessableError):
        await DescriptionLengthValidator().validate(_item(description="x" * 501))


# ── ValidationPipeline ───────────────────────────────────────────────────────

async def test_pipeline_passes_valid_item() -> None:
    pipeline = ValidationPipeline(
        NameNotEmptyValidator(),
        IdFormatValidator(),
        DescriptionLengthValidator(),
    )
    await pipeline.run(_item())


async def test_pipeline_stops_at_first_failure() -> None:
    call_order: list[str] = []

    class TrackingValidator:
        def __init__(self, label: str, should_fail: bool) -> None:
            self._label = label
            self._fail = should_fail

        async def validate(self, item: Item) -> None:
            call_order.append(self._label)
            if self._fail:
                raise UnprocessableError(self._label)

    pipeline = ValidationPipeline(
        TrackingValidator("first", should_fail=True),
        TrackingValidator("second", should_fail=False),
    )
    with pytest.raises(UnprocessableError, match="first"):
        await pipeline.run(_item())

    assert call_order == ["first"]


async def test_empty_pipeline_always_passes() -> None:
    await ValidationPipeline().run(_item())


async def test_pipeline_rejects_blank_name_before_bad_id() -> None:
    pipeline = ValidationPipeline(NameNotEmptyValidator(), IdFormatValidator())
    with pytest.raises(UnprocessableError, match="blank"):
        await pipeline.run(_item(name="", item_id="bad id!"))
