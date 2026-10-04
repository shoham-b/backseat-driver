"""The JSON error envelope every HTTP response of this project uses (the Google API error format).

The API's exception handlers and the report UI server both build their error bodies here, so a client sees the same
shape whichever of the two answered.
"""

from http import HTTPStatus
from typing import Any


def error_body(status: HTTPStatus, message: str) -> dict[str, Any]:
    return {"error": {"code": status, "status": status.phrase, "message": message}}
