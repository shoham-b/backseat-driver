from http import HTTPStatus

from fastapi import Request
from fastapi.responses import JSONResponse
from loguru import logger

from backseat_driver.api.errors import APIError
from backseat_driver.bl.errors import ConflictError, DomainError, NotFoundError, UnprocessableError

# Maps each concrete DomainError subclass to its HTTP status code.
# Add entries here as new domain errors are introduced in bl/errors.py.
_DOMAIN_STATUS: dict[type[DomainError], HTTPStatus] = {
    NotFoundError: HTTPStatus.NOT_FOUND,
    ConflictError: HTTPStatus.CONFLICT,
    UnprocessableError: HTTPStatus.UNPROCESSABLE_ENTITY,
}


def _json_error(status: HTTPStatus, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": status, "status": status.phrase, "message": message}},
    )


async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
    status = _DOMAIN_STATUS.get(type(exc), HTTPStatus.BAD_REQUEST)
    return _json_error(status, str(exc))


async def api_error_handler(request: Request, exc: APIError) -> JSONResponse:
    return _json_error(HTTPStatus(exc.status_code), exc.message)


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.opt(exception=exc).error("unhandled exception")
    return _json_error(HTTPStatus.INTERNAL_SERVER_ERROR, "internal server error")
