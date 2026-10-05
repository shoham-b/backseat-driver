from datetime import UTC, datetime
from typing import Any, Literal

from backseat_driver.models import DeadLetter

_MAX_ERROR_LENGTH = 500


def describe_failure(stage: str, error: BaseException) -> str:
    """What a failed job records: the stage and the exception, short enough for a database column and a response."""
    return f"{stage} failed: {type(error).__name__}: {error}"[:_MAX_ERROR_LENGTH]


def dead_letter_of(task: Literal["ingest", "caption"], payload: dict[str, Any], error: BaseException) -> DeadLetter:
    """The task that gave up, whole: the job's `error` is cut short and names no payload, so it can't be replayed."""
    return DeadLetter(task=task, payload=payload, error=f"{type(error).__name__}: {error}", failed_at=datetime.now(UTC))
