import json
from http import HTTPStatus

import pytest
from starlette.requests import Request

from backseat_driver.api.errors import APIError
from backseat_driver.api.exception_handlers import (
    api_error_handler,
    backseat_driver_error_handler,
    unhandled_exception_handler,
)
from backseat_driver.errors import BackseatDriverError, NotFoundError, UnprocessableError

_REQUEST = Request({"type": "http"})


class _UnmappedBackseatDriverError(BackseatDriverError):
    pass


@pytest.mark.parametrize(
    ("error", "status"),
    [
        (NotFoundError("gone"), HTTPStatus.NOT_FOUND),
        (UnprocessableError("bad"), HTTPStatus.UNPROCESSABLE_ENTITY),
        (BackseatDriverError("generic"), HTTPStatus.BAD_REQUEST),
        (_UnmappedBackseatDriverError("new kind"), HTTPStatus.BAD_REQUEST),
    ],
)
async def test_errors_map_to_their_http_status(error: BackseatDriverError, status: HTTPStatus) -> None:
    response = await backseat_driver_error_handler(_REQUEST, error)

    assert response.status_code == status
    expected = {"error": {"code": status, "status": status.phrase, "message": str(error)}}
    assert json.loads(bytes(response.body)) == expected


async def test_api_error_uses_its_own_status_and_message() -> None:
    response = await api_error_handler(_REQUEST, APIError("not ready", HTTPStatus.SERVICE_UNAVAILABLE))

    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert json.loads(bytes(response.body))["error"]["message"] == "not ready"


async def test_api_error_defaults_to_bad_request() -> None:
    response = await api_error_handler(_REQUEST, APIError("nope"))

    assert response.status_code == HTTPStatus.BAD_REQUEST


async def test_unhandled_exceptions_never_leak_their_message() -> None:
    response = await unhandled_exception_handler(_REQUEST, RuntimeError("secret connection string"))

    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    assert b"secret" not in bytes(response.body)
    assert json.loads(bytes(response.body))["error"]["message"] == "internal server error"
