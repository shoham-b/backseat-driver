from http import HTTPStatus

from fastapi import Request
from fastapi.responses import JSONResponse
from loguru import logger

from backseat_driver.api.errors import APIError
from backseat_driver.errors import BackseatDriverError, NotFoundError, UnprocessableError

# Maps each concrete BackseatDriverError subclass to its HTTP status code.
# Add entries here as new errors are introduced in errors.py.
_ERROR_STATUS: dict[type[BackseatDriverError], HTTPStatus] = {
    NotFoundError: HTTPStatus.NOT_FOUND,
    UnprocessableError: HTTPStatus.UNPROCESSABLE_ENTITY,
}


def _json_error(status: HTTPStatus, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": status, "status": status.phrase, "message": message}},
    )


async def backseat_driver_error_handler(request: Request, exc: BackseatDriverError) -> JSONResponse:
    status = _ERROR_STATUS.get(type(exc), HTTPStatus.BAD_REQUEST)
    return _json_error(status, str(exc))


async def api_error_handler(request: Request, exc: APIError) -> JSONResponse:
    return _json_error(HTTPStatus(exc.status_code), exc.message)


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.opt(exception=exc).error("unhandled exception")
    return _json_error(HTTPStatus.INTERNAL_SERVER_ERROR, "internal server error")
