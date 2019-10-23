# Platform Logging

Usage:
```python
    from platform_logging import init_logging
    import logging
    init_logging()
    
    logging.info("Some info")
```

By default `init_logging()` will forward all `errors` and `critical` messages to `stderr`. All other type of messages will be forwarded to `stdout`.
You can pass own dic-based config with custom setting.