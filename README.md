# Neuro Platform Logging

Usage:

```python
import logging

from neuro_logging import init_logging

init_logging()

logging.info("Some info")
```

By default `init_logging()` will forward all `errors` and `critical` messages to `stderr`. All other type of messages will be forwarded to `stdout`.
You can pass own dict-based config with custom setting i.e. for disable warning in asyncio and concurrent

```python
from neuro_logging import DEFAULT_CONFIG, init_logging

custom_config = dict(DEFAULT_CONFIG)
custom_config.update(
    {"loggers": {"asyncio": {"level": "ERROR"}, "concurrent": {"level": "ERROR"}}}
)

init_logging(custom_config)
```
