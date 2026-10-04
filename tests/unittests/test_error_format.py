from http import HTTPStatus

from backseat_driver.error_format import error_body


def test_the_body_follows_the_google_api_error_envelope() -> None:
    assert error_body(HTTPStatus.NOT_FOUND, "no such image") == {
        "error": {"code": 404, "status": "Not Found", "message": "no such image"}
    }
