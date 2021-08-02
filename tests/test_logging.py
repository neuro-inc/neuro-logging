import logging
import os
import re
from typing import Any

import pytest


try:
    os.environ["NP_LOG_LEVEL"] = "NOTSET"
    from neuro_logging import DEFAULT_CONFIG, HideLessThanFilter, init_logging
finally:
    del os.environ["NP_LOG_LEVEL"]


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


def test_custom_config(capsys: Any) -> None:
    custom_config = {
        "version": 1,
        "disable_existing_loggers": True,
        "handlers": {
            "stderr": {"class": "logging.StreamHandler", "level": logging.NOTSET}
        },
        "root": {"level": logging.NOTSET, "handlers": ["stderr"]},
    }
    init_logging(custom_config)
    _log_all_messages()
    captured = capsys.readouterr()
    assert "DebugMessage" in captured.err
    assert "InfoMessage" in captured.err
    assert "WarningMessage" in captured.err
    assert "ErrorMessage" in captured.err
    assert "CriticalMessage" in captured.err


def test_hide_less_filter_usage() -> None:
    filter = HideLessThanFilter(logging.INFO)
    record_info = logging.LogRecord("some", logging.INFO, "some", 12, "text", (), None)
    record_debug = logging.LogRecord(
        "some", logging.DEBUG, "some", 12, "text", (), None
    )
    assert filter.filter(record_info) is False
    assert filter.filter(record_debug) is True


def test_hide_less_filter_text_level_names() -> None:
    filter = HideLessThanFilter("INFO")
    assert filter.level == logging.INFO

    with pytest.raises(ValueError):
        HideLessThanFilter("unknown-level")


def test_existing_loggers_continue_work(capsys: Any) -> None:
    existing = logging.getLogger("existing")
    init_logging()

    existing.info("InfoMessage")
    existing.error("ErrorMessage")
    captured = capsys.readouterr()
    assert "InfoMessage" in captured.out
    assert "ErrorMessage" in captured.err


def test_rewrite_existing_logging(capsys: Any) -> None:
    existing = logging.getLogger("existing")

    config = dict(DEFAULT_CONFIG)
    config.update({"loggers": {"existing": {"level": "ERROR"}}})
    init_logging(config)

    existing.info("InfoMessage")
    existing.error("ErrorMessage")
    captured = capsys.readouterr()
    assert "InfoMessage" not in captured.out
    assert "InfoMessage" not in captured.err
    assert "ErrorMessage" in captured.err
