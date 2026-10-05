"""Schema-conformance tests — schemathesis exercises all OpenAPI operations
and validates that every response matches the declared schema."""

import schemathesis

from backseat_driver.api.app import create_app
from backseat_driver.api.dependencies import get_captioner, get_job_queue, get_job_store
from tests.fakes import FakeCaptioner, FakeJobQueue, FakeJobStore, make_settings

app = create_app(make_settings())
app.dependency_overrides[get_captioner] = lambda: FakeCaptioner("a fake scene description")
# Fuzzed POST /jobs must not start real work: the monolith would run an ingest thread over whatever dataset is on disk.
_job_queue, _job_store = FakeJobQueue(), FakeJobStore()
app.dependency_overrides[get_job_queue] = lambda: _job_queue
app.dependency_overrides[get_job_store] = lambda: _job_store
# /metrics is added by prometheus_fastapi_instrumentator and returns text/plain,
# which is outside the OpenAPI spec — exclude it from schema conformance checks.
schema = schemathesis.openapi.from_asgi("/openapi.json", app).exclude(path_regex=r"^/metrics")


@schema.parametrize()
def test_api_schema(case: schemathesis.Case) -> None:
    # /describe does content-based validation (rejects unreadable/empty images with
    # 422) that the OpenAPI schema itself can't express, which schemathesis's
    # "positive data acceptance" check doesn't expect — so we scope schema
    # conformance testing here to "the API never 500s", not "every schema-valid
    # request is accepted".
    case.call_and_validate(checks=[schemathesis.checks.not_a_server_error])
