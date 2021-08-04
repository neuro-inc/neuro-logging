import asyncio
import functools
import logging
import sys
from contextlib import asynccontextmanager
from contextvars import ContextVar
from types import SimpleNamespace
from typing import (
    Any,
    AsyncIterator,
    Awaitable,
    Callable,
    Dict,
    Iterable,
    List,
    Mapping,
    Optional,
    Sequence,
    Type,
    TypeVar,
    cast,
)

import aiohttp
import aiozipkin
import pkg_resources
import sentry_sdk
from aiohttp import (
    ClientSession,
    TraceConfig,
    TraceRequestEndParams,
    TraceRequestExceptionParams,
    TraceRequestStartParams,
    web,
)
from aiohttp.web import AbstractRoute
from aiozipkin.aiohttp_helpers import set_context_value, zipkin_context
from aiozipkin.span import SpanAbc
from aiozipkin.transport import Transport
from sentry_sdk import Hub
from sentry_sdk.integrations.aiohttp import AioHttpIntegration
from yarl import URL


Handler = Callable[[web.Request], Awaitable[web.StreamResponse]]


CURRENT_TRACER: ContextVar[aiozipkin.Tracer] = ContextVar("CURRENT_TRACER")
CURRENT_SPAN: ContextVar[SpanAbc] = ContextVar("CURRENT_SPAN")


T = TypeVar("T", bound=Callable[..., Awaitable[Any]])


@asynccontextmanager
async def new_zipkin_trace_cm(
    name: str, sampled: Optional[bool]
) -> AsyncIterator[Optional[SpanAbc]]:
    tracer = CURRENT_TRACER.get(None)
    if tracer is None:
        # No tracer is set,
        # the call is made from unittest most likely.
        yield None
        return

    span = tracer.new_trace(sampled=sampled)

    with set_context_value(zipkin_context, span.context):
        with span:
            span.name(name)
            reset_token = CURRENT_SPAN.set(span)
            try:
                yield span
            finally:
                CURRENT_SPAN.reset(reset_token)


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
    async with new_zipkin_trace_cm(name, sampled):
        async with new_sentry_trace_cm(name, sampled):
            yield


@asynccontextmanager
async def zipkin_trace_cm(name: str) -> AsyncIterator[Optional[SpanAbc]]:
    tracer = CURRENT_TRACER.get(None)
    if tracer is None:
        # No tracer is set,
        # the call is made from unittest most likely.
        yield None
        return
    try:
        span = CURRENT_SPAN.get()
    except LookupError:
        yield None
        return
    child = tracer.new_child(span.context)
    reset_token = CURRENT_SPAN.set(child)
    try:
        with child:
            child.name(name)
            yield child
    finally:
        CURRENT_SPAN.reset(reset_token)


@asynccontextmanager
async def sentry_trace_cm(
    name: str,
    tags: Optional[Mapping[str, str]] = None,
    data: Optional[Mapping[str, Any]] = None,
) -> AsyncIterator[Optional[sentry_sdk.tracing.Span]]:
    parent_span = sentry_sdk.Hub.current.scope.span
    if parent_span is None:
        # No tracer is set,
        # the call is made from unittest most likely.
        yield None
    else:
        # Hub manages context vars and should be created per each span
        with Hub(Hub.current) as hub:
            parent_span = hub.scope.span

            if parent_span is None:
                yield None
                return

            with parent_span.start_child(op="call", description=name) as child:
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
    async with zipkin_trace_cm(name):
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


@web.middleware
async def store_zipkin_span_middleware(
    request: web.Request, handler: Handler
) -> web.StreamResponse:  # pragma: no cover
    span = aiozipkin.request_span(request)
    CURRENT_SPAN.set(span)
    return await handler(request)


def setup_zipkin_tracer(
    app_name: str,
    host: str,
    port: int,
    zipkin_url: URL,
    sample_rate: float = 0.01,
    send_interval: float = 5,
    ignored_exceptions: Optional[List[Type[Exception]]] = None,
) -> None:
    endpoint = aiozipkin.create_endpoint(app_name, ipv4=host, port=port)
    sampler = aiozipkin.Sampler(sample_rate=sample_rate)
    transport = Transport(str(zipkin_url / "api/v2/spans"), send_interval=send_interval)
    tracer = aiozipkin.Tracer(transport, sampler, endpoint, ignored_exceptions)
    CURRENT_TRACER.set(tracer)


def setup_zipkin(
    app: web.Application,
    *,
    skip_routes: Optional[Iterable[AbstractRoute]] = None,
) -> None:  # pragma: no cover
    tracer = CURRENT_TRACER.get(None)

    if tracer is None:
        raise Exception(
            "Tracer was not initialized. Please setup tracer before calling this method"
        )

    aiozipkin.setup(app, tracer, skip_routes=skip_routes)
    app.middlewares.append(store_zipkin_span_middleware)


def _make_sentry_before_send(
    exclude: Sequence[Type[BaseException]] = (),
) -> Callable[[Dict[str, Any], Any], Optional[Dict[str, Any]]]:
    exceptions = tuple(exclude) + (
        asyncio.CancelledError,
        aiohttp.ServerConnectionError,
    )

    def _sentry_before_send(
        event: Dict[str, Any],
        hint: Any,
    ) -> Optional[Dict[str, Any]]:
        exc_info = hint.get("exc_info")
        if exc_info is not None:
            exc_typ, exc_val, tb = exc_info
            if isinstance(exc_val, exceptions):
                return None
        return event

    return _sentry_before_send


def _find_caller_version() -> str:
    caller = sys._getframe(1)
    package, sep, tail = caller.f_globals["__package__"].partition(".")
    version = pkg_resources.get_distribution(package).version
    return f"{package}@{version}"


def setup_sentry(
    sentry_dsn: URL,
    app_name: str,
    cluster_name: str,
    sample_rate: float,
    *,
    exclude: Sequence[Type[BaseException]] = (),
) -> None:  # pragma: no cover
    sentry_sdk.init(
        dsn=str(sentry_dsn) or None,
        traces_sample_rate=sample_rate,
        integrations=[AioHttpIntegration(transaction_style="method_and_path_pattern")],
        before_send=_make_sentry_before_send(exclude),
        release=_find_caller_version(),
        environment=cluster_name,
    )
    sentry_sdk.set_tag("app", app_name)
    sentry_sdk.set_tag("cluster", cluster_name)


def make_zipkin_trace_config() -> aiohttp.TraceConfig:  # pragma: no cover
    tracer = CURRENT_TRACER.get(None)

    if tracer is None:
        raise Exception(
            "Tracer was not initialized. Please setup tracer before calling this method"
        )

    return aiozipkin.make_trace_config(tracer)


def make_sentry_trace_config() -> TraceConfig:
    """
    Creates aiohttp.TraceConfig with enabled Sentry distributive tracing
    for aiohttp client.
    """

    async def on_request_start(
        session: ClientSession,
        context: SimpleNamespace,
        params: TraceRequestStartParams,
    ) -> None:
        hub = Hub.current

        parent_span = hub.scope.span
        if parent_span is None:
            return

        # Hub manages context vars and should be created per each span
        hub = Hub(hub)
        context._hub = hub
        hub.__enter__()

        span_name = f"{params.method.upper()} {params.url.path}"
        span = parent_span.start_child(op="client", description=span_name)
        context._span = span
        span.__enter__()

        ctx = context.trace_request_ctx
        propagate_headers = ctx is None or getattr(ctx, "propagate_headers", True)

        if propagate_headers:
            params.headers.update(span.iter_headers())

    async def on_request_end(
        session: ClientSession, context: SimpleNamespace, params: TraceRequestEndParams
    ) -> None:
        hub = getattr(context, "_hub", None)

        if not hub:
            return

        hub.__exit__(None, None, None)
        del context._hub

        span = context._span
        span.__exit__(None, None, None)
        del context._span

    async def on_request_exception(
        session: ClientSession,
        context: SimpleNamespace,
        params: TraceRequestExceptionParams,
    ) -> None:
        hub = getattr(context, "_hub", None)

        if not hub:
            return

        exc = params.exception

        hub.__exit__(type(exc), exc, exc.__traceback__)
        del context._hub

        span = context._span
        span.__exit__(type(exc), exc, exc.__traceback__)
        del context._span

    trace_config = TraceConfig()
    trace_config.on_request_start.append(on_request_start)
    trace_config.on_request_end.append(on_request_end)
    trace_config.on_request_exception.append(on_request_exception)

    return trace_config


def make_request_logging_trace_config(
    logger: Optional[logging.Logger] = None,
) -> TraceConfig:
    log = logger or logging.getLogger(__name__)

    assert log

    async def on_request_start(
        session: ClientSession,
        trace_config_ctx: SimpleNamespace,
        params: TraceRequestStartParams,
    ) -> None:
        log.info("Sending %s %s", params.method, params.url)

    async def on_request_end(
        session: ClientSession,
        trace_config_ctx: SimpleNamespace,
        params: TraceRequestEndParams,
    ) -> None:
        if 400 <= params.response.status:
            log.warning(
                "Received %s %s %s: %s",
                params.method,
                params.response.status,
                params.url,
                await params.response.text(),
            )
        else:
            log.info(
                "Received %s %s %s", params.method, params.response.status, params.url
            )

    trace_config = TraceConfig()
    trace_config.on_request_start.append(on_request_start)
    trace_config.on_request_end.append(on_request_end)

    return trace_config
