from http import HTTPStatus

from backseat_driver.api.errors import APIError


def test_api_error_default_status() -> None:
    err = APIError("something went wrong")

    assert err.message == "something went wrong"
    assert err.status_code == HTTPStatus.BAD_REQUEST


def test_api_error_custom_status() -> None:
    err = APIError("not found", HTTPStatus.NOT_FOUND)

    assert err.message == "not found"
    assert err.status_code == HTTPStatus.NOT_FOUND
