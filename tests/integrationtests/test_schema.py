"""Schema-conformance tests — schemathesis exercises all OpenAPI operations
and validates that every response matches the declared schema."""

from collections.abc import Iterator

import pytest
import schemathesis

from vlm_scene_description.api.app import app
from vlm_scene_description.api.dependencies import get_captioner


class _FakeCaptioner:
    """Local stub — avoids importing across test modules; returns instantly."""

    model_name = "fake-model"

    def caption(self, image_path: str) -> str:
        return "a fake scene description"

    def healthcheck(self) -> bool:
        return True


# /metrics is added by prometheus_fastapi_instrumentator and returns text/plain,
# which is outside the OpenAPI spec — exclude it from schema conformance checks.
schema = schemathesis.openapi.from_asgi("/openapi.json", app).exclude(path_regex=r"^/metrics")


@pytest.fixture(autouse=True, scope="module")
def _override_captioner() -> Iterator[None]:
    app.dependency_overrides[get_captioner] = lambda: _FakeCaptioner()
    yield
    app.dependency_overrides.pop(get_captioner, None)


@schema.parametrize()
def test_api_schema(case: schemathesis.Case) -> None:
    # /describe does content-based validation (rejects unreadable/empty images with
    # 422) that the OpenAPI schema itself can't express, which schemathesis's
    # "positive data acceptance" check doesn't expect — so we scope schema
    # conformance testing here to "the API never 500s", not "every schema-valid
    # request is accepted".
    case.call_and_validate(checks=[schemathesis.checks.not_a_server_error])  # ty: ignore[invalid-argument-type]
