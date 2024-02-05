import logging
import os
import re
from typing import Any

import pytest

from neuro_logging import AllowLessThanFilter, init_logging


@pytest.fixture(autouse=True)
def set_log_level() -> None:
    os.environ["LOG_LEVEL"] = "NOTSET"


def _log_all_messages() -> None:
    logging.debug("DebugMessage")
    logging.info("InfoMessage")
    logging.warning("WarningMessage")
    logging.error("ErrorMessage")
    logging.critical("CriticalMessage")


def test_default_config_format(capsys: Any) -> None:
    init_logging()
    logging.debug("DebugMessage")
    captured = capsys.readouterr()
    assert re.match(
        r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d+ - root - DEBUG - DebugMessage",
        captured.out,
    )


def test_default_config_output(capsys: Any) -> None:
    init_logging()
    _log_all_messages()
    captured = capsys.readouterr()
    assert "DebugMessage" in captured.out
    assert "InfoMessage" in captured.out
    assert "WarningMessage" in captured.out
    assert "ErrorMessage" in captured.err
    assert "CriticalMessage" in captured.err


def test_health_checks_filtered(capsys: Any) -> None:
    init_logging()
    logging.getLogger("aiohttp.access").info("InfoMessage")
    logging.getLogger("aiohttp.access").info("GET /api/v1/ping")
    captured = capsys.readouterr()
    assert "InfoMessage" in captured.out
    assert "/api/v1/ping" not in captured.out


def test_health_checks_filtered__error(capsys: Any) -> None:
    init_logging()
    logging.getLogger("aiohttp.access").error("GET /api/v1/ping")
    captured = capsys.readouterr()
    assert "/api/v1/ping" in captured.err


def test_health_checks_filtered__custom_url_path(capsys: Any) -> None:
    init_logging(health_check_url_path="/health")
    logging.getLogger("aiohttp.access").info("GET /health")
    captured = capsys.readouterr()
    assert not captured.out


def test_allow_less_filter_usage() -> None:
    filter = AllowLessThanFilter(logging.INFO)
    record_info = logging.LogRecord("some", logging.INFO, "some", 12, "text", (), None)
    record_debug = logging.LogRecord(
        "some", logging.DEBUG, "some", 12, "text", (), None
    )
    assert filter.filter(record_info) is False
    assert filter.filter(record_debug) is True


def test_allow_less_filter_text_level_names() -> None:
    filter = AllowLessThanFilter("INFO")
    assert filter.level == logging.INFO

    with pytest.raises(ValueError):
        AllowLessThanFilter("unknown-level")


def test_existing_loggers_continue_work(capsys: Any) -> None:
    existing = logging.getLogger("existing")
    init_logging()

    existing.info("InfoMessage")
    existing.error("ErrorMessage")
    captured = capsys.readouterr()
    assert "InfoMessage" in captured.out
    assert "ErrorMessage" in captured.err
