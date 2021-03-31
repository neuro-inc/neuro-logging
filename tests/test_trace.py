import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Awaitable, Callable

import aiohttp
import aiohttp.web
import aiozipkin
import pytest
import sentry_sdk
from aiohttp.test_utils import TestServer
from aiozipkin.helpers import TraceContext
from aiozipkin.span import NoopSpan
from sentry_sdk.tracing import Transaction
from yarl import URL

from platform_logging import init_logging
from platform_logging.trace import (
    CURRENT_SPAN,
    CURRENT_TRACER,
    create_zipkin_tracer,
    make_request_logging_trace_config,
    make_sentry_trace_config,
    notrace,
    trace,
)


@asynccontextmanager
async def setup_zipkin_tracer() -> AsyncIterator[aiozipkin.Tracer]:
    tracer = await create_zipkin_tracer("test", "zipkin", 80, URL("zipkin"), 1.0)
    token = CURRENT_TRACER.set(tracer)
    yield tracer
    CURRENT_TRACER.reset(token)


@asynccontextmanager
async def setup_zipkin_span(
    tracer: aiozipkin.Tracer,
) -> AsyncIterator[aiozipkin.SpanAbc]:
    context = TraceContext(
        parent_id=None,
        trace_id="trace",
        span_id="span",
        sampled=None,
        debug=False,
        shared=False,
    )
    span = NoopSpan(tracer, context)
    token = CURRENT_SPAN.set(span)
    yield span
    CURRENT_SPAN.reset(token)


def create_new_sentry_transaction() -> None:
    transaction = sentry_sdk.Hub.current.start_transaction(
        Transaction(name="test", parent_sampled=True, sampled=True)
    )
    sentry_sdk.Hub.current.scope.span = transaction.start_child()


@pytest.fixture
async def server(
    aiohttp_server: Callable[[aiohttp.web.Application], Awaitable[TestServer]]
) -> AsyncIterator[TestServer]:
    async def handle(request: aiohttp.web.Request) -> aiohttp.web.Response:
        request.app["headers"] = request.headers
        return aiohttp.web.Response()

    app = aiohttp.web.Application()
    app.add_routes([aiohttp.web.get("/", handle)])

    yield await aiohttp_server(app)


async def test_zipkin_trace() -> None:
    async with setup_zipkin_tracer() as tracer:
        async with setup_zipkin_span(tracer) as span:
            parent_span = span

            @trace
            async def func() -> None:
                span = CURRENT_SPAN.get()

                assert parent_span != span

            await func()


async def test_zipkin_trace_no_tracer() -> None:
    @trace
    async def func() -> None:
        span = CURRENT_SPAN.get(None)

        assert span is None

    await func()


async def test_zipkin_trace_no_parent_span() -> None:
    @trace
    async def func() -> None:
        span = CURRENT_SPAN.get(None)

        assert span is not None

    async with setup_zipkin_tracer():
        await func()


async def test_sentry_trace() -> None:
    sentry_sdk.init(traces_sample_rate=1.0)
    create_new_sentry_transaction()
    parent_span = sentry_sdk.Hub.current.scope.span

    @trace
    async def func() -> None:
        span = sentry_sdk.Hub.current.scope.span

        assert span
        assert parent_span != span
        assert span.op == "call"
        assert span.description == "test_sentry_trace.<locals>.func"

    await func()


async def test_sentry_trace_without_parent_span() -> None:
    sentry_sdk.init(traces_sample_rate=1.0)
    sentry_sdk.Hub.current.scope.span = None

    @trace
    async def func() -> None:
        assert sentry_sdk.Hub.current.scope.span is None

    await func()


async def test_sentry_notrace() -> None:
    @notrace
    async def func() -> None:
        assert not sentry_sdk.Hub.current.scope.transaction.sampled

    sentry_sdk.init(traces_sample_rate=1.0)
    create_new_sentry_transaction()

    assert sentry_sdk.Hub.current.scope.transaction.sampled

    await func()


async def test_sentry_trace_config(server: TestServer) -> None:
    sentry_sdk.init(traces_sample_rate=1.0)
    create_new_sentry_transaction()

    trace_config = make_sentry_trace_config()

    async with aiohttp.ClientSession(trace_configs=[trace_config]) as client:
        await client.get(URL.build(host=server.host, port=server.port))

        assert "sentry-trace" in server.app["headers"]


async def test_sentry_trace_config_no_header(server: TestServer) -> None:
    sentry_sdk.init(traces_sample_rate=1.0)
    sentry_sdk.Hub.current.scope.span = None

    trace_config = make_sentry_trace_config()

    async with aiohttp.ClientSession(trace_configs=[trace_config]) as client:
        await client.get(URL.build(host=server.host, port=server.port))

        assert "sentry-trace" not in server.app["headers"]


async def test_request_logging_trace_config(server: TestServer, capsys: Any) -> None:
    init_logging()
    trace_config = make_request_logging_trace_config(logging.getLogger(__name__))

    async with aiohttp.ClientSession(trace_configs=[trace_config]) as client:
        await client.get(URL.build(host=server.host, port=server.port))

    captured = capsys.readouterr()
    assert "Sending" in captured.out
    assert "Received" in captured.out
