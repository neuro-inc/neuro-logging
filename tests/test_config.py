import logging

from neuro_logging.config import EnvironConfigFactory


class TestEnvironConfigFactory:
    def test_create_logging__defaults(self) -> None:
        config = EnvironConfigFactory({}).create_logging()

        assert config.log_level == logging.INFO
        assert not config.log_health_check

    def test_create_logging__custom(self) -> None:
        environ = {
            "LOG_LEVEL": "error",
            "LOG_HEALTH_CHECK": "1",
        }
        config = EnvironConfigFactory(environ).create_logging()

        assert config.log_level == logging.ERROR
        assert config.log_health_check

    def test_create_sentry__defaults(self) -> None:
        config = EnvironConfigFactory({}).create_sentry()

        assert config
        assert config.dsn is None
        assert config.cluster_name is None
        assert config.app_name is None
        assert config.sample_rate == 0.1

    def test_create_sentry__custom(self) -> None:
        environ = {
            "SENTRY_DSN": "sentry-dsn",
            "SENTRY_CLUSTER_NAME": "cluster",
            "SENTRY_APP_NAME": "app",
            "SENTRY_SAMPLE_RATE": "0.5",
        }
        config = EnvironConfigFactory(environ).create_sentry()

        assert config
        assert config.dsn == "sentry-dsn"
        assert config.cluster_name == "cluster"
        assert config.app_name == "app"
        assert config.sample_rate == 0.5
