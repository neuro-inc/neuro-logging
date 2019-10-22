import logging
import logging.config
from pathlib import Path
from typing import Union

import yaml

from .version import VERSION


__version__ = VERSION

__all__ = ["init_logging", "HideLessThanFilter"]

DEFAULT_CONFIG_FILE = Path(__file__).parent / "config.yaml"


def init_logging(config_file_name: Union[str, Path] = DEFAULT_CONFIG_FILE) -> None:
    with open(config_file_name, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
        logging.config.dictConfig(config)


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
