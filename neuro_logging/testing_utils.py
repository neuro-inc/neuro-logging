# shim file for testing purpose,
# _find_caller_version() should be called from a package

from neuro_logging.trace import _find_caller_version


def _get_test_version() -> str:
    return _find_caller_version()
