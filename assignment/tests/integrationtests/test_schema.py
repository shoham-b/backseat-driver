"""Schema-conformance tests — schemathesis exercises all OpenAPI operations
and validates that every response matches the declared schema."""
from collections.abc import Iterator

import pytest
import schemathesis

from vlm_scene_description.api.app import app
from vlm_scene_description.api.dependencies import get_repository
from vlm_scene_description.db.memory import MemoryRepository

# /metrics is added by prometheus_fastapi_instrumentator and returns text/plain,
# which is outside the OpenAPI spec — exclude it from schema conformance checks.
# /items is an example router — remove this exclusion once you replace it with your own routes.
schema = (
    schemathesis.openapi.from_asgi("/openapi.json", app)
    .exclude(path_regex=r"^/metrics")
    .exclude(path_regex=r"^/items")
)


@pytest.fixture(autouse=True, scope="module")
def _override_repository() -> Iterator[None]:
    app.dependency_overrides[get_repository] = lambda: MemoryRepository()
    yield
    app.dependency_overrides.pop(get_repository, None)


@schema.parametrize()
def test_api_schema(case: schemathesis.Case) -> None:
    case.call_and_validate()
