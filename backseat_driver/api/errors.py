from http import HTTPStatus
from typing import Any

from pydantic import BaseModel


class APIError(Exception):
    def __init__(self, message: str, status_code: int = HTTPStatus.BAD_REQUEST) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class ErrorDetail(BaseModel):
    code: int
    status: str
    message: str


class ErrorResponse(BaseModel):
    """The OpenAPI model of `error_format.error_body`, which the exception handlers build."""

    error: ErrorDetail


# FastAPI's own request validation answers 422 in its `detail` format, so 422 is deliberately not declared here.
NOT_FOUND_RESPONSE: dict[int | str, dict[str, Any]] = {HTTPStatus.NOT_FOUND: {"model": ErrorResponse}}
UNAVAILABLE_RESPONSE: dict[int | str, dict[str, Any]] = {HTTPStatus.SERVICE_UNAVAILABLE: {"model": ErrorResponse}}
