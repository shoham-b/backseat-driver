import json
import logging
import sys
from collections.abc import Iterator

import pytest
from loguru import logger

from backseat_driver.logger import LogFormat, setup_logging


@pytest.fixture(autouse=True)
def _restore_logger() -> Iterator[None]:
    root_handlers = logging.root.handlers[:]
    yield
    logging.root.handlers[:] = root_handlers
    logger.remove()
    logger.configure(extra={})
    logger.add(sys.stderr)  # loguru's own default, so later tests still see log output


def test_json_format_emits_one_serialized_record_with_the_service(capsys: pytest.CaptureFixture[str]) -> None:
    setup_logging(LogFormat.JSON, service="api")

    logger.bind(request_id="r-1").info("hello")
    record = json.loads(capsys.readouterr().err.strip())["record"]

    assert record["message"] == "hello"
    assert record["extra"] == {"service": "api", "request_id": "r-1"}


def test_colored_format_shows_service_and_message(capsys: pytest.CaptureFixture[str]) -> None:
    setup_logging(LogFormat.COLORED, service="cli")

    logger.info("hello there")
    err = capsys.readouterr().err

    assert "cli" in err
    assert "hello there" in err


def test_default_service_name_is_the_package(capsys: pytest.CaptureFixture[str]) -> None:
    setup_logging(LogFormat.JSON)

    logger.info("x")

    assert json.loads(capsys.readouterr().err.strip())["record"]["extra"]["service"] == "backseat_driver"


def test_calling_setup_twice_does_not_duplicate_output(capsys: pytest.CaptureFixture[str]) -> None:
    setup_logging(LogFormat.JSON)
    setup_logging(LogFormat.JSON)

    logger.info("once")

    assert len(capsys.readouterr().err.strip().splitlines()) == 1


def test_log_format_values_match_the_settings_literals() -> None:
    assert {f.value for f in LogFormat} == {"colored", "json"}


def test_stdlib_logging_is_routed_into_loguru_with_level_and_service(capsys: pytest.CaptureFixture[str]) -> None:
    setup_logging(LogFormat.JSON, service="worker")

    logging.getLogger("celery.app.trace").error("Task ingest raised %s", "boom")
    record = json.loads(capsys.readouterr().err.strip())["record"]

    assert record["message"] == "Task ingest raised boom"
    assert record["level"]["name"] == "ERROR"
    assert record["extra"]["service"] == "worker"


def test_stdlib_exception_info_is_preserved(capsys: pytest.CaptureFixture[str]) -> None:
    setup_logging(LogFormat.JSON)

    try:
        raise RuntimeError("kaput")
    except RuntimeError:
        logging.getLogger("celery.worker").exception("task failed")
    record = json.loads(capsys.readouterr().err.strip())["record"]

    assert record["exception"]["type"] == "RuntimeError"


def test_stdlib_records_with_a_custom_level_name_still_log(capsys: pytest.CaptureFixture[str]) -> None:
    setup_logging(LogFormat.JSON)
    logging.addLevelName(25, "NOTICE")

    logging.getLogger("x").log(25, "heads up")
    record = json.loads(capsys.readouterr().err.strip())["record"]

    assert record["message"] == "heads up"
