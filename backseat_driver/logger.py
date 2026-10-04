import logging
import sys
from enum import StrEnum

from loguru import logger


class LogFormat(StrEnum):
    COLORED = "colored"
    JSON = "json"


class _InterceptHandler(logging.Handler):
    """Forwards stdlib `logging` records (Celery, SQLAlchemy, ...) into loguru so they share its sinks and format."""

    def emit(self, record: logging.LogRecord) -> None:
        level: str | int
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno  # custom stdlib level that loguru has no name for; log by number

        # Walk out of the logging module's own frames (their count varies with the call path:
        # logging.info(), LoggerAdapter, warnings capture) so loguru reports the original caller.
        frame, depth = logging.currentframe(), 0
        while frame and (depth == 0 or frame.f_code.co_filename == logging.__file__):
            frame = frame.f_back
            depth += 1
        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def setup_logging(fmt: LogFormat = LogFormat.COLORED, service: str = "backseat_driver") -> None:
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
    # Without this, a worker that fails a task logs nothing: Celery reports through stdlib logging, not loguru.
    logging.basicConfig(handlers=[_InterceptHandler()], level=logging.INFO, force=True)
    logging.captureWarnings(True)
