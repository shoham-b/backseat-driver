_MAX_ERROR_LENGTH = 500


def describe_failure(stage: str, error: BaseException) -> str:
    """What a failed job records: the stage and the exception, short enough for a database column and a response."""
    return f"{stage} failed: {type(error).__name__}: {error}"[:_MAX_ERROR_LENGTH]
