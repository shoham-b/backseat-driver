import re

import pytest
from hypothesis import given
from hypothesis import strategies as st

from backseat_driver.api.middleware import resolve_transaction_id

_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def test_a_missing_header_gets_a_generated_uuid() -> None:
    assert _UUID.fullmatch(resolve_transaction_id(None))


@pytest.mark.parametrize("header", ["my-trace-id", "a.b_c-1", "x" * 128, "550e8400-e29b-41d4-a716-446655440000"])
def test_a_safe_token_is_kept(header: str) -> None:
    assert resolve_transaction_id(header) == header


@pytest.mark.parametrize("header", ["", "x" * 129, "has space", "line\nbreak", "semi;colon", "ünïcode", '{"a": 1}'])
def test_anything_else_is_replaced_by_a_generated_uuid(header: str) -> None:
    assert _UUID.fullmatch(resolve_transaction_id(header))


@given(st.text())
def test_the_result_is_always_a_safe_token(header: str) -> None:
    resolved = resolve_transaction_id(header)

    assert re.fullmatch(r"[A-Za-z0-9._-]{1,128}", resolved)
