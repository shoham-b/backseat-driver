import re
import uuid
from collections.abc import Awaitable, Callable

from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

REQUEST_ID_HEADER = "X-Request-ID"

# The id ends up in a database column, queue messages and every log line, so a client can't choose just anything.
_VALID_ID = re.compile(r"[A-Za-z0-9._-]{1,128}")


def resolve_transaction_id(header: str | None) -> str:
    """The caller's `X-Request-ID` when it is a safe token, else a generated uuid."""
    if header is None:
        return str(uuid.uuid4())
    if _VALID_ID.fullmatch(header) is None:
        logger.warning("ignoring a malformed {} header ({} characters)", REQUEST_ID_HEADER, len(header))
        return str(uuid.uuid4())
    return header


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        transaction_id = resolve_transaction_id(request.headers.get(REQUEST_ID_HEADER))
        # Read by endpoints that hand the id on, e.g. through queue messages.
        request.state.transaction_id = transaction_id
        # Bound as `transaction_id`, the name the workers log it under, so one query follows it across services.
        with logger.contextualize(transaction_id=transaction_id):
            response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = transaction_id
        return response
