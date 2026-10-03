"""Error types — keep domain code free of HTTP concepts.

Raise these from domain code. api/exception_handlers.py translates
them into HTTP 4xx responses, so domain code never imports from fastapi or http.
"""


class BackseatDriverError(Exception):
    """Base for all business-logic errors."""


class NotFoundError(BackseatDriverError):
    """The requested resource does not exist."""


class UnprocessableError(BackseatDriverError):
    """Input is syntactically valid but violates domain rules."""
