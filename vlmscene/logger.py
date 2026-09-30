import sys
from enum import StrEnum

from loguru import logger


class LogFormat(StrEnum):
    COLORED = "colored"
    JSON = "json"


def setup_logging(fmt: LogFormat = LogFormat.COLORED, service: str = "vlmscene") -> None:
    logger.configure(extra={"service": service})
    logger.remove()
    if fmt == LogFormat.JSON:
        logger.add(sys.stderr, serialize=True)
    else:
        logger.add(
            sys.stderr,
            colorize=True,
            format=(
                "<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | "
                "<blue>{extra[service]}</blue> | "
                "<cyan>{name}</cyan>:<cyan>{line}</cyan> — <level>{message}</level>"
            ),
        )
