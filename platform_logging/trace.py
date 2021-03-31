import functools
import logging
from contextlib import asynccontextmanager
from contextvars import ContextVar
from types import SimpleNamespace
from typing import (
    Any,
    AsyncIterator,
    Awaitable,
    Callable,
    Iterable,
    Optional,
    TypeVar,
    cast,
)

import aiozipkin
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
from aiozipkin.span import SpanAbc
from sentry_sdk.integrations.aiohttp import AioHttpIntegration
from yarl import URL


Handler = Callable[[web.Request], Awaitable[web.StreamResponse]]


CURRENT_TRACER: ContextVar[aiozipkin.Tracer] = ContextVar("CURRENT_TRACER")
CURRENT_SPAN: ContextVar[SpanAbc] = ContextVar("CURRENT_SPAN")


T = TypeVar("T", bound=Callable[..., Awaitable[Any]])


@asynccontextmanager
async def zipkin_tracing_cm(name: str) -> AsyncIterator[Optional[SpanAbc]]:
    tracer = CURRENT_TRACER.get(None)
    if tracer is None:
        # No tracer is set,
        # the call is made from unittest most likely.
        yield None
        return
    try:
        span = CURRENT_SPAN.get()
        child = tracer.new_child(span.context)
    except LookupError:
        child = tracer.new_trace(sampled=False)
    reset_token = CURRENT_SPAN.set(child)
    try:
        with child:
            child.name(name)
            yield child
    finally:
        CURRENT_SPAN.reset(reset_token)


@asynccontextmanager
async def sentry_tracing_cm(
    name: str,
) -> AsyncIterator[Optional[sentry_sdk.tracing.Span]]:
    parent_span = sentry_sdk.Hub.current.scope.span
    if parent_span is None:
        # No tracer is set,
        # the call is made from unittest most likely.
        yield None
    else:
        with parent_span.start_child(op="call", description=name) as child:
            yield child


@asynccontextmanager
async def tracing_cm(name: str) -> AsyncIterator[None]:
    async with zipkin_tracing_cm(name):
        async with sentry_tracing_cm(name):
            yield


def trace(func: T) -> T:
    @functools.wraps(func)
    async def tracer(*args: Any, **kwargs: Any) -> Any:
        name = func.__qualname__
        async with tracing_cm(name):
            return await func(*args, **kwargs)

    return cast(T, tracer)


def notrace(func: T) -> T:
    @functools.wraps(func)
    async def tracer(*args: Any, **kwargs: Any) -> Any:
        with sentry_sdk.Hub.current.configure_scope() as scope:
            transaction = scope.transaction
            if transaction is not None:
                transaction.sampled = False
            return await func(*args, **kwargs)

    return cast(T, tracer)


@web.middleware
async def store_zipkin_span_middleware(
    request: web.Request, handler: Handler
) -> web.StreamResponse:  # pragma: no cover
    tracer = aiozipkin.get_tracer(request.app)
    span = aiozipkin.request_span(request)
    CURRENT_TRACER.set(tracer)
    CURRENT_SPAN.set(span)
    return await handler(request)


async def create_zipkin_tracer(
    app_name: str, host: str, port: int, zipkin_url: URL, sample_rate: float
) -> aiozipkin.Tracer:
    endpoint = aiozipkin.create_endpoint(app_name, ipv4=host, port=port)

    return await aiozipkin.create(
        str(zipkin_url / "api/v2/spans"), endpoint, sample_rate=sample_rate
    )


def setup_zipkin(
    app: web.Application,
    tracer: aiozipkin.Tracer,
    *,
    skip_routes: Optional[Iterable[AbstractRoute]] = None,
) -> None:  # pragma: no cover
    aiozipkin.setup(app, tracer, skip_routes=skip_routes)
    app.middlewares.append(store_zipkin_span_middleware)


def setup_sentry(
    sentry_dsn: URL, app_name: str, cluster_name: str, sample_rate: float
) -> None:  # pragma: no cover
    sentry_sdk.init(
        dsn=str(sentry_dsn) or None,
        traces_sample_rate=sample_rate,
        integrations=[AioHttpIntegration(transaction_style="method_and_path_pattern")],
    )
    sentry_sdk.set_tag("app", app_name)
    sentry_sdk.set_tag("cluster", cluster_name)


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
        parent_span = sentry_sdk.Hub.current.scope.span
        if parent_span is None:
            return

        span_name = f"{params.method.upper()} {params.url.path}"
        span = parent_span.start_child(op="client", description=span_name)
        context._span = span
        span.__enter__()

        ctx = context.trace_request_ctx
        propagate_headers = ctx is None or ctx.get("propagate_headers", True)
        if propagate_headers:
            params.headers.update(span.iter_headers())

    async def on_request_end(
        session: ClientSession, context: SimpleNamespace, params: TraceRequestEndParams
    ) -> None:
        parent_span = sentry_sdk.Hub.current.scope.span
        if parent_span is None:
            return

        span = context._span
        span.__exit__(None, None, None)
        del context._span

    async def on_request_exception(
        session: ClientSession,
        context: SimpleNamespace,
        params: TraceRequestExceptionParams,
    ) -> None:
        parent_span = sentry_sdk.Hub.current.scope.span
        if parent_span is None:  # pragma: no cover
            return

        span = context._span
        exc = params.exception
        span.__exit__(type(exc), exc, exc.__traceback__)
        del context._span

    trace_config = TraceConfig()
    trace_config.on_request_start.append(on_request_start)
    trace_config.on_request_end.append(on_request_end)
    trace_config.on_request_exception.append(on_request_exception)

    return trace_config


def make_request_logging_trace_config(logger: logging.Logger) -> TraceConfig:
    async def on_request_start(
        session: ClientSession,
        trace_config_ctx: SimpleNamespace,
        params: TraceRequestStartParams,
    ) -> None:
        logger.info("Sending %s %s", params.method, params.url)

    async def on_request_end(
        session: ClientSession,
        trace_config_ctx: SimpleNamespace,
        params: TraceRequestEndParams,
    ) -> None:
        if 400 <= params.response.status:
            logger.warning(
                "Received %s %s %s: %s",
                params.method,
                params.response.status,
                params.url,
                await params.response.text(),
            )
        else:
            logger.info(
                "Received %s %s %s", params.method, params.response.status, params.url
            )

    trace_config = TraceConfig()
    trace_config.on_request_start.append(on_request_start)
    trace_config.on_request_end.append(on_request_end)

    return trace_config
