import asyncio
import functools
import inspect
import logging
from collections.abc import AsyncIterator, Awaitable, Callable, Iterable, Mapping
from contextlib import asynccontextmanager
from importlib.metadata import version
from typing import Any, Optional, TypeVar, Union, cast

import aiohttp
import sentry_sdk
from sentry_sdk import Hub
from sentry_sdk.integrations.aiohttp import AioHttpIntegration
from yarl import URL

from .config import EnvironConfigFactory

LOGGER = logging.getLogger(__name__)


T = TypeVar("T", bound=Callable[..., Awaitable[Any]])


@asynccontextmanager
async def new_sentry_trace_cm(
    name: str, sampled: Optional[bool]
) -> AsyncIterator[sentry_sdk.tracing.Span]:
    with Hub(Hub.current) as hub:
        with hub.configure_scope() as scope:
            scope.clear_breadcrumbs()

        with hub.start_transaction(name=name, sampled=sampled) as transaction:
            try:
                yield transaction
            except asyncio.CancelledError:
                transaction.set_status("cancelled")
                raise
            except Exception as exc:
                hub.capture_exception(error=exc)
                raise


@asynccontextmanager
async def new_trace_cm(
    name: str, sampled: Optional[bool] = None
) -> AsyncIterator[None]:
    async with new_sentry_trace_cm(name, sampled):
        yield


@asynccontextmanager
async def sentry_trace_cm(
    name: str,
    tags: Optional[Mapping[str, str]] = None,
    data: Optional[Mapping[str, Any]] = None,
) -> AsyncIterator[Optional[sentry_sdk.tracing.Span]]:
    with Hub(Hub.current) as hub:
        with hub.start_span(op="call", description=name) as child:
            if tags:
                for key, value in tags.items():
                    child.set_tag(key, value)
            if data:
                for key, value in data.items():
                    child.set_data(key, value)
            try:
                yield child
            except asyncio.CancelledError:
                child.set_status("cancelled")
                raise
            except Exception as exc:
                hub.capture_exception(error=exc)
                raise


@asynccontextmanager
async def trace_cm(
    name: str,
    tags: Optional[Mapping[str, str]] = None,
    data: Optional[Mapping[str, str]] = None,
) -> AsyncIterator[None]:
    async with sentry_trace_cm(name, tags=tags, data=data):
        yield


def trace(func: T) -> T:
    async def _tracer(*args: Any, **kwargs: Any) -> Any:
        name = func.__qualname__
        async with trace_cm(name):
            return await func(*args, **kwargs)

    @functools.wraps(func)
    async def tracer(*args: Any, **kwargs: Any) -> Any:
        # Create a task to wrap method call to avoid scope data leakage between calls.
        return await asyncio.create_task(_tracer(*args, **kwargs))

    return cast(T, tracer)


def new_trace(func: T) -> T:
    async def _tracer(*args: Any, **kwargs: Any) -> Any:
        name = func.__qualname__
        async with new_trace_cm(name):
            return await func(*args, **kwargs)

    @functools.wraps(func)
    async def tracer(*args: Any, **kwargs: Any) -> Any:
        # Create a task to wrap method call to avoid scope data leakage between calls.
        return await asyncio.create_task(_tracer(*args, **kwargs))

    return cast(T, tracer)


def new_sampled_trace(func: T) -> T:
    async def _tracer(*args: Any, **kwargs: Any) -> Any:
        name = func.__qualname__
        async with new_trace_cm(name, sampled=True):
            return await func(*args, **kwargs)

    @functools.wraps(func)
    async def tracer(*args: Any, **kwargs: Any) -> Any:
        # Create a task to wrap method call to avoid scope data leakage between calls.
        return await asyncio.create_task(_tracer(*args, **kwargs))

    return cast(T, tracer)


def notrace(func: T) -> T:
    @functools.wraps(func)
    async def tracer(*args: Any, **kwargs: Any) -> Any:
        with Hub.current.configure_scope() as scope:
            transaction = scope.transaction
            if transaction is not None:
                transaction.sampled = False
            return await func(*args, **kwargs)

    return cast(T, tracer)


def before_send_transaction(
    event: dict[str, Any], hint: Any, *, health_check_url_path: str
) -> Optional[dict[str, Any]]:
    url = URL(event["request"]["url"])

    if url.path == health_check_url_path:
        return None

    return event


def _find_caller_version(stacklevel: int) -> str:
    caller = inspect.currentframe()
    assert caller is not None
    while stacklevel:
        caller = caller.f_back
        stacklevel -= 1
        assert caller is not None
    package, sep, tail = caller.f_globals["__package__"].partition(".")
    ver = version(package)
    return f"{package}@{ver}"


def setup_sentry(
    *,
    health_check_url_path: str = "/api/v1/ping",
    ignore_errors: Iterable[Union[type[BaseException], str]] = (),
) -> None:  # pragma: no cover
    config = EnvironConfigFactory().create_sentry()
    LOGGER.info("Loaded Sentry config: %s", config)
    ignore_errors = tuple(ignore_errors) + (
        asyncio.CancelledError,
        aiohttp.ServerConnectionError,
        ConnectionResetError,
    )
    sentry_sdk.init(
        dsn=str(config.dsn) or None,
        traces_sample_rate=config.sample_rate,
        integrations=[AioHttpIntegration(transaction_style="method_and_path_pattern")],
        ignore_errors=ignore_errors,
        before_send_transaction=functools.partial(
            before_send_transaction, health_check_url_path=health_check_url_path
        ),
        release=_find_caller_version(2),
        environment=config.cluster_name,
    )
    if config.app_name:
        sentry_sdk.set_tag("app", config.app_name)
    if config.cluster_name:
        sentry_sdk.set_tag("cluster", config.cluster_name)
