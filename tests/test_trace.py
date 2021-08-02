import asyncio
import logging
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any, AsyncIterator, Awaitable, Callable, List, Optional

import aiohttp
import aiohttp.web
import aiozipkin
import pytest
import sentry_sdk
from aiohttp.test_utils import TestServer
from aiozipkin.helpers import TraceContext
from aiozipkin.span import NoopSpan
from sentry_sdk.tracing import Span, Transaction
from yarl import URL

from neuro_logging import init_logging
from neuro_logging.trace import (
    CURRENT_SPAN,
    CURRENT_TRACER,
    make_request_logging_trace_config,
    make_sentry_trace_config,
    new_sampled_trace,
    new_trace,
    notrace,
    setup_zipkin_tracer as _setup_zipkin_tracer,
    trace,
    trace_cm,
)


def setup_zipkin_tracer(
    sample_rate: float = 1,
) -> None:
    _setup_zipkin_tracer("test", "zipkin", 80, URL("zipkin"), sample_rate)


@asynccontextmanager
async def setup_zipkin_span() -> AsyncIterator[aiozipkin.SpanAbc]:
    context = TraceContext(
        parent_id=None,
        trace_id="trace",
        span_id="span",
        sampled=None,
        debug=False,
        shared=False,
    )
    tracer = CURRENT_TRACER.get()
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


def make_sentry_span_collector_trace_config() -> aiohttp.TraceConfig:
    async def on_request_start(
        session: aiohttp.ClientSession,
        context: SimpleNamespace,
        params: aiohttp.TraceRequestStartParams,
    ) -> None:
        context.trace_request_ctx.span = sentry_sdk.Hub.current.scope.span

    trace_config = aiohttp.TraceConfig()
    trace_config.on_request_start.append(on_request_start)

    return trace_config


async def test_zipkin_trace() -> None:
    setup_zipkin_tracer()

    async with setup_zipkin_span() as span:
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

        assert span is None

    setup_zipkin_tracer()

    await func()


async def test_zipkin_new_trace() -> None:
    setup_zipkin_tracer()

    with pytest.raises(LookupError):
        CURRENT_SPAN.get()

    @new_trace
    async def func() -> None:
        span = CURRENT_SPAN.get()

        assert span

    await func()


async def test_zipkin_new_trace_no_tracer() -> None:
    @new_trace
    async def func() -> None:
        with pytest.raises(LookupError):
            CURRENT_SPAN.get()

    await func()


async def test_zipkin_new_sampled_trace() -> None:
    setup_zipkin_tracer(sample_rate=0)

    with pytest.raises(LookupError):
        CURRENT_SPAN.get()

    @new_sampled_trace
    async def func() -> None:
        span = CURRENT_SPAN.get()

        assert span.context.sampled is True

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


async def test_sentry_trace_cm_data() -> None:
    sentry_sdk.init(traces_sample_rate=1.0)
    create_new_sentry_transaction()

    async with trace_cm(
        "test", tags={"test1": "val1", "test2": "val2"}, data={"data": "value"}
    ):

        span = sentry_sdk.Hub.current.scope.span

        assert span
        assert span._tags["test1"] == "val1"
        assert span._tags["test2"] == "val2"
        assert span._data["data"] == "value"


async def test_sentry_trace_multiple_tasks() -> None:
    sentry_sdk.init(traces_sample_rate=1.0)
    create_new_sentry_transaction()
    parent_span = sentry_sdk.Hub.current.scope.span
    spans = []

    assert parent_span

    @trace
    async def func() -> None:
        await asyncio.sleep(0)
        span = sentry_sdk.Hub.current.scope.span

        assert span

        spans.append(span)

    await asyncio.gather(func(), func())

    span1, span2 = spans

    assert span1.span_id != span2.span_id
    assert span1.parent_span_id == parent_span.span_id
    assert span2.parent_span_id == parent_span.span_id


async def test_sentry_trace_without_parent_span() -> None:
    sentry_sdk.init(traces_sample_rate=1.0)
    sentry_sdk.Hub.current.scope.span = None

    @trace
    async def func() -> None:
        assert sentry_sdk.Hub.current.scope.span is None

    await func()


async def test_sentry_new_trace() -> None:
    sentry_sdk.init(traces_sample_rate=1.0)

    @new_trace
    async def func() -> None:
        span = sentry_sdk.Hub.current.scope.span

        assert isinstance(span, Transaction)
        assert span.name == "test_sentry_new_trace.<locals>.func"

    await func()


async def test_sentry_new_trace_multiple_tasks() -> None:
    sentry_sdk.init(traces_sample_rate=1.0)
    spans: List[Optional[Span]] = []

    @new_trace
    async def func() -> None:
        await asyncio.sleep(0)
        span = sentry_sdk.Hub.current.scope.span

        spans.append(span)

    await asyncio.gather(func(), func())

    span1, span2 = spans

    assert span1
    assert span2
    assert span1.trace_id != span2.trace_id


async def test_sentry_new_sampled_trace() -> None:
    sentry_sdk.init(traces_sample_rate=0)

    @new_sampled_trace
    async def func() -> None:
        span = sentry_sdk.Hub.current.scope.span

        assert isinstance(span, Transaction)
        assert span.name == "test_sentry_new_sampled_trace.<locals>.func"
        assert span.sampled is True

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
        current_span = sentry_sdk.Hub.current.scope.span

        await client.get(URL.build(host=server.host, port=server.port))

        assert "sentry-trace" in server.app["headers"]
        assert current_span == sentry_sdk.Hub.current.scope.span


async def test_sentry_trace_config_explicit_trace_ctx(server: TestServer) -> None:
    sentry_sdk.init(traces_sample_rate=1.0)
    create_new_sentry_transaction()

    trace_config = make_sentry_trace_config()

    async with aiohttp.ClientSession(trace_configs=[trace_config]) as client:
        current_span = sentry_sdk.Hub.current.scope.span

        ctx = SimpleNamespace()
        ctx.propagate_headers = False

        await client.get(
            URL.build(host=server.host, port=server.port), trace_request_ctx=ctx
        )

        assert "sentry-trace" not in server.app["headers"]
        assert current_span == sentry_sdk.Hub.current.scope.span


async def test_sentry_trace_config_multiple_tasks(server: TestServer) -> None:
    sentry_sdk.init(traces_sample_rate=1.0)
    create_new_sentry_transaction()

    trace_configs = [
        make_sentry_trace_config(),
        make_sentry_span_collector_trace_config(),
    ]

    async with aiohttp.ClientSession(trace_configs=trace_configs) as client:
        current_span = sentry_sdk.Hub.current.scope.span

        ctx1 = SimpleNamespace()
        ctx2 = SimpleNamespace()

        await asyncio.gather(
            client.get(
                URL.build(host=server.host, port=server.port),
                trace_request_ctx=ctx1,
            ),
            client.get(
                URL.build(host=server.host, port=server.port),
                trace_request_ctx=ctx2,
            ),
        )

        assert current_span
        assert current_span == sentry_sdk.Hub.current.scope.span
        assert ctx1.span.span_id != ctx2.span.span_id
        assert ctx1.span.parent_span_id == current_span.span_id
        assert ctx2.span.parent_span_id == current_span.span_id


async def test_sentry_trace_config_no_header(server: TestServer) -> None:
    sentry_sdk.init(traces_sample_rate=1.0)
    sentry_sdk.Hub.current.scope.span = None

    trace_config = make_sentry_trace_config()

    async with aiohttp.ClientSession(trace_configs=[trace_config]) as client:
        await client.get(URL.build(host=server.host, port=server.port))

        assert "sentry-trace" not in server.app["headers"]


async def test_sentry_trace_config_exception(server: TestServer) -> None:
    sentry_sdk.init(traces_sample_rate=1.0)
    create_new_sentry_transaction()

    trace_config = make_sentry_trace_config()

    async with aiohttp.ClientSession(trace_configs=[trace_config]) as client:
        current_span = sentry_sdk.Hub.current.scope.span

        with pytest.raises(Exception):
            await client.get(URL.build(host="unknown", port=server.port))

        assert current_span == sentry_sdk.Hub.current.scope.span


async def test_request_logging_trace_config(server: TestServer, capsys: Any) -> None:
    init_logging()
    trace_config = make_request_logging_trace_config(logging.getLogger(__name__))

    async with aiohttp.ClientSession(trace_configs=[trace_config]) as client:
        await client.get(URL.build(host=server.host, port=server.port))

    captured = capsys.readouterr()
    assert "Sending GET" in captured.out
    assert "Received GET 200" in captured.out


async def test_request_logging_trace_config_error(
    server: TestServer, capsys: Any
) -> None:
    init_logging()
    trace_config = make_request_logging_trace_config(logging.getLogger(__name__))

    async with aiohttp.ClientSession(trace_configs=[trace_config]) as client:
        await client.get(URL.build(host=server.host, port=server.port, path="/unknown"))

    captured = capsys.readouterr()
    assert "Sending GET" in captured.out
    assert "Received GET 404" in captured.out
