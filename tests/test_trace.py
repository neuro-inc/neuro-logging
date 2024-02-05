import asyncio
import re
import typing as t

import pytest
import sentry_sdk
from sentry_sdk.tracing import Span, Transaction

from neuro_logging.testing_utils import _get_test_version
from neuro_logging.trace import (
    before_send_transaction,
    new_sampled_trace,
    new_trace,
    notrace,
    trace,
    trace_cm,
)


@pytest.fixture()
def sentry_transaction() -> t.Iterator[None]:
    sentry_sdk.init(traces_sample_rate=1.0)
    hub = sentry_sdk.Hub.current
    with sentry_sdk.Hub(hub) as hub:
        with hub.start_transaction(
            Transaction(name="test", hub=hub, parent_sampled=True, sampled=True)
        ):
            yield


@pytest.mark.usefixtures("sentry_transaction")
async def test_sentry_trace() -> None:
    parent_span = sentry_sdk.Hub.current.scope.span

    @trace
    async def func() -> None:
        span = sentry_sdk.Hub.current.scope.span

        assert span
        assert parent_span != span
        assert span.op == "call"
        assert span.description == "test_sentry_trace.<locals>.func"

    await func()


@pytest.mark.usefixtures("sentry_transaction")
async def test_sentry_trace_cm_data() -> None:
    async with trace_cm(
        "test", tags={"test1": "val1", "test2": "val2"}, data={"data": "value"}
    ):

        span = sentry_sdk.Hub.current.scope.span

        assert span
        assert span._tags["test1"] == "val1"
        assert span._tags["test2"] == "val2"
        assert span._data["data"] == "value"


@pytest.mark.usefixtures("sentry_transaction")
async def test_sentry_trace_multiple_tasks() -> None:
    spans = []

    @trace
    async def func() -> None:
        await asyncio.sleep(0)
        span = sentry_sdk.Hub.current.scope.span

        assert span

        spans.append(span)

    await asyncio.gather(func(), func())

    span1, span2 = spans

    assert span1.span_id != span2.span_id


async def test_sentry_new_trace() -> None:
    @new_trace
    async def func() -> None:
        span = sentry_sdk.Hub.current.scope.span

        assert isinstance(span, Transaction)
        assert span.name == "test_sentry_new_trace.<locals>.func"

    sentry_sdk.init(traces_sample_rate=1.0)

    await func()


async def test_sentry_new_trace_multiple_tasks() -> None:
    sentry_sdk.init(traces_sample_rate=1.0)
    spans: list[t.Optional[Span]] = []

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
    @new_sampled_trace
    async def func() -> None:
        span = sentry_sdk.Hub.current.scope.span

        assert isinstance(span, Transaction)
        assert span.name == "test_sentry_new_sampled_trace.<locals>.func"
        assert span.sampled is True

    sentry_sdk.init(traces_sample_rate=1.0)

    await func()


@pytest.mark.usefixtures("sentry_transaction")
async def test_sentry_notrace() -> None:
    @notrace
    async def func() -> None:
        assert not sentry_sdk.Hub.current.scope.transaction.sampled

    assert sentry_sdk.Hub.current.scope.transaction.sampled

    await func()


def test_find_caller_version() -> None:
    version = _get_test_version()
    assert re.match(r"^neuro_logging@\d+[.]\d+", version)


def test_sentry_before_send_transaction() -> None:
    event = before_send_transaction(
        {"request": {"url": "http://127.0.0.1/api/v1/ping"}},
        None,
        health_check_url_path="/api/v1/ping",
    )
    assert event is None

    event = before_send_transaction(
        {"request": {"url": "http://127.0.0.1/api/v1/jobs"}},
        None,
        health_check_url_path="/api/v1/ping",
    )
    assert event is not None
