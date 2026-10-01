from collections.abc import Iterator

import pytest
from loguru import logger


@pytest.fixture(autouse=True)
def _silence_logging() -> Iterator[None]:
    """Keep log sinks out of the measurements: benchmarks time the domain code, not stderr writes."""
    logger.disable("backseat_driver")
    yield
    logger.enable("backseat_driver")
