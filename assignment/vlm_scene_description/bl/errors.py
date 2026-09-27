"""Domain error types — keep BL free of HTTP concepts.

Raise these from business-logic code. api/exception_handlers.py translates
them into HTTP 4xx responses, so BL code never imports from fastapi or http.
"""


class DomainError(Exception):
    """Base for all business-logic errors."""


class NotFoundError(DomainError):
    """The requested resource does not exist."""


class ConflictError(DomainError):
    """The operation conflicts with existing state (e.g. duplicate key)."""


class UnprocessableError(DomainError):
    """Input is syntactically valid but violates domain rules."""
