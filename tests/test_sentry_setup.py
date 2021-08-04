import re_assert

from neuro_logging.testing_utils import _get_test_version


def test_caller_version() -> None:
    version = _get_test_version()
    assert version == re_assert.Matches(r"^neuro_logging@\d+[.]\d+")
