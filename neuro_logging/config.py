from __future__ import annotations

import logging
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class LoggingConfig:
    log_level: int = logging.INFO
    log_health_check: bool = False
    health_check_url_path: str = "/api/v1/ping"


@dataclass(frozen=True)
class SentryConfig:
    dsn: str | None = None
    cluster_name: str | None = None
    app_name: str | None = None
    sample_rate: float = 0.1
    health_check_path: str = "/api/v1/ping"


def _to_bool(value: str) -> bool:
    return value.lower() in ("true", "1", "yes", "y")


class EnvironConfigFactory:
    def __init__(self, environ: dict[str, str] | None = None) -> None:
        self._environ = environ or os.environ

    def create_logging(self) -> LoggingConfig:
        return LoggingConfig(
            log_level=logging.getLevelName(
                self._environ.get(
                    "LOG_LEVEL",
                    logging.getLevelName(LoggingConfig.log_level),
                ).upper()
            ),
            log_health_check=_to_bool(self._environ.get("LOG_HEALTH_CHECK", "0")),
            health_check_url_path=self._environ.get(
                "LOG_HEALTH_CHECK_URL_PATH", LoggingConfig.health_check_url_path
            ),
        )

    def create_sentry(self) -> SentryConfig:
        return SentryConfig(
            dsn=self._environ.get("SENTRY_DSN"),
            cluster_name=self._environ.get(
                "SENTRY_CLUSTER_NAME", SentryConfig.cluster_name
            ),
            app_name=self._environ.get("SENTRY_APP_NAME", SentryConfig.app_name),
            sample_rate=float(
                self._environ.get("SENTRY_SAMPLE_RATE", SentryConfig.sample_rate)
            ),
            health_check_path=self._environ.get(
                "SENTRY_HEALTH_CHECK_PATH", SentryConfig.health_check_path
            ),
        )
