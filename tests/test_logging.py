import json
import logging
import os
import re
from typing import Any
from unittest import mock

import pytest
from dirty_equals import IsList, IsNow, IsPartialDict, IsPositiveInt, IsStr

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


def test_json_logging_with_extra(capsys: Any, monkeypatch: Any) -> None:
    monkeypatch.delenv("PYTEST_VERSION")
    init_logging()
    logging.debug("msg", extra={"key": "first"})
    captured = capsys.readouterr()
    assert not captured.err
    msg = json.loads(captured.out)
    assert msg == IsPartialDict(
        {
            "args": [],
            "exc_info": None,
            "filename": "test_logging.py",
            "funcName": "test_json_logging_with_extra",
            "key": "first",
            "lineno": IsPositiveInt(),
            "logName": "root",
            "message": "msg",
            "module": "test_logging",
            "pathname": mock.ANY,
            "process": IsPositiveInt(),
            "processName": "MainProcess",
            "severity": "DEBUG",
            "stack_info": None,
            "thread": IsPositiveInt(),
            "threadName": "MainThread",
            "timestamp": mock.ANY,
        }
    )


def test_json_logging_with_args(capsys: Any, monkeypatch: Any) -> None:
    monkeypatch.delenv("PYTEST_VERSION")
    init_logging()
    logging.debug("%s msg", "arg")
    captured = capsys.readouterr()
    assert not captured.err
    msg = json.loads(captured.out)
    assert msg == IsPartialDict(
        {
            "args": ["arg"],
            "exc_info": None,
            "filename": "test_logging.py",
            "funcName": "test_json_logging_with_args",
            "lineno": IsPositiveInt(),
            "logName": "root",
            "message": "arg msg",
            "module": "test_logging",
            "pathname": mock.ANY,
            "process": IsPositiveInt(),
            "processName": "MainProcess",
            "severity": "DEBUG",
            "stack_info": None,
            "thread": IsPositiveInt(),
            "threadName": "MainThread",
            "timestamp": IsNow(tz="UTC", iso_string=True),
        }
    )


def test_json_logging_with_exc_info(capsys: Any, monkeypatch: Any) -> None:
    monkeypatch.delenv("PYTEST_VERSION")
    init_logging()
    try:
        1 / 0
    except ZeroDivisionError:
        logging.debug("%s msg", "arg", exc_info=True)
    captured = capsys.readouterr()
    assert not captured.err
    msg = json.loads(captured.out)
    assert msg == IsPartialDict(
        {
            "args": ["arg"],
            "exc_info": IsList(
                "ZeroDivisionError",
                "ZeroDivisionError: division by zero",
                length=3,
            ),
            "filename": "test_logging.py",
            "funcName": "test_json_logging_with_exc_info",
            "lineno": IsPositiveInt(),
            "logName": "root",
            "message": "arg msg",
            "module": "test_logging",
            "pathname": mock.ANY,
            "process": IsPositiveInt(),
            "processName": "MainProcess",
            "severity": "DEBUG",
            "stack_info": None,
            "thread": IsPositiveInt(),
            "threadName": "MainThread",
            "timestamp": IsNow(tz="UTC", iso_string=True),
        }
    )


def test_json_logging_with_stack_info(capsys: Any, monkeypatch: Any) -> None:
    monkeypatch.delenv("PYTEST_VERSION")
    init_logging()
    logging.debug("%s msg", "arg", stack_info=True)
    captured = capsys.readouterr()
    assert not captured.err
    msg = json.loads(captured.out)
    import pprint

    pprint.pprint(msg)
    assert msg == IsPartialDict(
        {
            "args": ["arg"],
            "exc_info": None,
            "filename": "test_logging.py",
            "funcName": "test_json_logging_with_stack_info",
            "lineno": IsPositiveInt(),
            "logName": "root",
            "message": "arg msg",
            "module": "test_logging",
            "pathname": mock.ANY,
            "process": IsPositiveInt(),
            "processName": "MainProcess",
            "severity": "DEBUG",
            "stack_info": IsStr(),
            "thread": IsPositiveInt(),
            "threadName": "MainThread",
            "timestamp": IsNow(tz="UTC", iso_string=True),
        }
    )
    assert msg["stack_info"].startswith("Stack (most recent call last):\n")
