import logging
import logging.config
from typing import Any, Dict, Union

from .trace import (
    make_request_logging_trace_config,
    make_sentry_trace_config,
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
from .version import VERSION


__version__ = VERSION

__all__ = [
    "init_logging",
    "HideLessThanFilter",
    "setup_zipkin_tracer",
    "make_request_logging_trace_config",
    "make_sentry_trace_config",
    "notrace",
    "setup_sentry",
    "setup_zipkin",
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


DEFAULT_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {"format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"}
    },
    "filters": {
        "hide_errors": {"()": "platform_logging.HideLessThanFilter", "level": "ERROR"}
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
    "root": {"level": logging.NOTSET, "handlers": ["stderr", "stdout"]},
}


def init_logging(config: Dict[str, Any] = DEFAULT_CONFIG) -> None:
    logging.config.dictConfig(config)
