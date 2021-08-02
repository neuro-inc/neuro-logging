import logging
import logging.config
import os
from typing import Any, Dict, Union

from pkg_resources import get_distribution

from .trace import (
    make_request_logging_trace_config,
    make_sentry_trace_config,
    make_zipkin_trace_config,
    new_sampled_trace,
    new_trace,
    new_trace_cm,
    notrace,
    setup_sentry,
    setup_zipkin,
    setup_zipkin_tracer,
    trace,
    trace_cm,
)


__version__ = get_distribution(__name__).version

__all__ = [
    "init_logging",
    "HideLessThanFilter",
    "make_request_logging_trace_config",
    "make_sentry_trace_config",
    "make_zipkin_trace_config",
    "notrace",
    "setup_sentry",
    "setup_zipkin",
    "setup_zipkin_tracer",
    "trace",
    "trace_cm",
    "new_sampled_trace",
    "new_trace",
    "new_trace_cm",
]


class HideLessThanFilter(logging.Filter):
    def __init__(self, level: Union[int, str] = logging.ERROR, name: str = ""):
        super().__init__(name)
        if not isinstance(level, int):
            try:
                level = logging._nameToLevel[level]
            except KeyError:
                raise ValueError(f"Unknown level name: {level}")
        self.level = level

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno < self.level


if "NP_LOG_LEVEL" in os.environ:
    _default_log_level = logging.getLevelName(os.environ["NP_LOG_LEVEL"])
else:
    _default_log_level = logging.WARNING


DEFAULT_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {"format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"}
    },
    "filters": {
        "hide_errors": {"()": f"{__name__}.HideLessThanFilter", "level": "ERROR"}
    },
    "handlers": {
        "stdout": {
            "class": "logging.StreamHandler",
            "level": "DEBUG",
            "formatter": "standard",
            "stream": "ext://sys.stdout",
            "filters": ["hide_errors"],
        },
        "stderr": {
            "class": "logging.StreamHandler",
            "level": "ERROR",
            "formatter": "standard",
            "stream": "ext://sys.stderr",
        },
    },
    "root": {"level": _default_log_level, "handlers": ["stderr", "stdout"]},
}


def init_logging(config: Dict[str, Any] = DEFAULT_CONFIG) -> None:
    logging.config.dictConfig(config)
