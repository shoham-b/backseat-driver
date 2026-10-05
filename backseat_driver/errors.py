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


class IdempotencyKeyInUseError(BackseatDriverError):
    """A job was already created under this idempotency key."""

    def __init__(self, key: str) -> None:
        super().__init__(f"idempotency key {key!r} is already used")
        self.key = key


class HttpStatusError(RuntimeError):
    """An HTTP call we made was answered with an error status.

    It carries the status so the caller can pass it on: the report UI answers a missing image with a 404 instead of
    reporting every upstream failure as a bad gateway. Not a `BackseatDriverError`, because it is not about the domain
    and the API must not map it to a status of its own.
    """

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
