"""Unit tests for ResilientTransport (RFC-0030)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

import httpx
import pytest

from gradle_deps_monitor.infrastructure._shared.http import (
    HttpPolicy,
    ResilientTransport,
    make_resilient_client,
)


def _seq_transport(responses: list[httpx.Response]) -> httpx.MockTransport:
    """Mock transport that returns *responses* one per call, then a 500."""
    iterator = iter(responses)

    def handler(_request: httpx.Request) -> httpx.Response:
        try:
            return next(iterator)
        except StopIteration:
            return httpx.Response(500)

    return httpx.MockTransport(handler)


class _NoopSleep:
    """Replaces ``asyncio.sleep`` in tests; records every delay it was given."""

    def __init__(self) -> None:
        self.delays: list[float] = []

    async def __call__(self, delay: float) -> None:
        self.delays.append(delay)


def _no_jitter() -> float:
    """Deterministic jitter — always returns 1.0 (full backoff window)."""
    return 1.0


# ---------------------------------------------------------------------------
# Happy path — pass-through behaviour
# ---------------------------------------------------------------------------


async def test_returns_2xx_on_first_attempt(tmp_path: object) -> None:
    inner = _seq_transport([httpx.Response(200, text="ok")])
    sleep = _NoopSleep()
    transport = ResilientTransport(policy=HttpPolicy(max_attempts=3), inner=inner, sleep=sleep)
    async with httpx.AsyncClient(transport=transport) as client:
        response = await client.get("https://example/api")
    assert response.status_code == 200
    assert sleep.delays == []  # no retries → no sleeps


async def test_returns_non_retryable_4xx_immediately() -> None:
    """404 / 401 / 403 (non-rate-limit) must not trigger retries."""
    inner = _seq_transport([httpx.Response(404)])
    sleep = _NoopSleep()
    transport = ResilientTransport(policy=HttpPolicy(max_attempts=3), inner=inner, sleep=sleep)
    async with httpx.AsyncClient(transport=transport) as client:
        response = await client.get("https://example/missing")
    assert response.status_code == 404
    assert sleep.delays == []


# ---------------------------------------------------------------------------
# Retry on transient failures
# ---------------------------------------------------------------------------


async def test_retries_on_429_then_succeeds() -> None:
    inner = _seq_transport([httpx.Response(429), httpx.Response(200)])
    sleep = _NoopSleep()
    transport = ResilientTransport(
        policy=HttpPolicy(max_attempts=3, backoff_base_seconds=2.0),
        inner=inner,
        sleep=sleep,
        jitter=_no_jitter,
    )
    async with httpx.AsyncClient(transport=transport) as client:
        response = await client.get("https://example/api")
    assert response.status_code == 200
    assert sleep.delays == [2.0]  # base * 2^0 * jitter(1.0)


async def test_retries_on_503_then_succeeds() -> None:
    inner = _seq_transport([httpx.Response(503), httpx.Response(200)])
    sleep = _NoopSleep()
    transport = ResilientTransport(
        policy=HttpPolicy(max_attempts=2),
        inner=inner,
        sleep=sleep,
        jitter=_no_jitter,
    )
    async with httpx.AsyncClient(transport=transport) as client:
        response = await client.get("https://example/api")
    assert response.status_code == 200
    assert len(sleep.delays) == 1


async def test_exhausts_after_max_attempts_returns_last_response() -> None:
    """After ``max_attempts`` retryable responses, the last one is returned."""
    inner = _seq_transport([httpx.Response(503), httpx.Response(503), httpx.Response(503)])
    sleep = _NoopSleep()
    transport = ResilientTransport(
        policy=HttpPolicy(max_attempts=3), inner=inner, sleep=sleep, jitter=_no_jitter
    )
    async with httpx.AsyncClient(transport=transport) as client:
        response = await client.get("https://example/api")
    assert response.status_code == 503
    assert len(sleep.delays) == 2  # 3 attempts → 2 sleeps between


# ---------------------------------------------------------------------------
# Network errors
# ---------------------------------------------------------------------------


async def test_retries_on_request_error_then_succeeds() -> None:
    """`httpx.RequestError` triggers retry, then success returns."""
    call_count = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise httpx.ConnectError("simulated network blip")
        return httpx.Response(200, text="ok")

    inner = httpx.MockTransport(handler)
    sleep = _NoopSleep()
    transport = ResilientTransport(
        policy=HttpPolicy(max_attempts=3), inner=inner, sleep=sleep, jitter=_no_jitter
    )
    async with httpx.AsyncClient(transport=transport) as client:
        response = await client.get("https://example/api")
    assert response.status_code == 200
    assert call_count["n"] == 2
    assert len(sleep.delays) == 1


async def test_raises_request_error_after_max_attempts() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("perma-dead host")

    inner = httpx.MockTransport(handler)
    sleep = _NoopSleep()
    transport = ResilientTransport(policy=HttpPolicy(max_attempts=2), inner=inner, sleep=sleep)
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(httpx.ConnectError):
            await client.get("https://example/api")
    assert len(sleep.delays) == 1  # one sleep between two attempts


# ---------------------------------------------------------------------------
# Retry-After header
# ---------------------------------------------------------------------------


async def test_retry_after_seconds_overrides_backoff() -> None:
    inner = _seq_transport([httpx.Response(429, headers={"Retry-After": "7"}), httpx.Response(200)])
    sleep = _NoopSleep()
    transport = ResilientTransport(
        policy=HttpPolicy(max_attempts=3, backoff_base_seconds=1.0, backoff_max_seconds=60.0),
        inner=inner,
        sleep=sleep,
        jitter=_no_jitter,
    )
    async with httpx.AsyncClient(transport=transport) as client:
        await client.get("https://example/api")
    assert sleep.delays == [7.0]


async def test_retry_after_capped_at_backoff_max() -> None:
    inner = _seq_transport(
        [httpx.Response(429, headers={"Retry-After": "999"}), httpx.Response(200)]
    )
    sleep = _NoopSleep()
    transport = ResilientTransport(
        policy=HttpPolicy(max_attempts=3, backoff_max_seconds=5.0),
        inner=inner,
        sleep=sleep,
    )
    async with httpx.AsyncClient(transport=transport) as client:
        await client.get("https://example/api")
    assert sleep.delays == [5.0]


async def test_retry_after_http_date_honored() -> None:
    future = datetime.now(tz=UTC) + timedelta(seconds=4)
    http_date = format_datetime(future, usegmt=True)
    inner = _seq_transport(
        [httpx.Response(503, headers={"Retry-After": http_date}), httpx.Response(200)]
    )
    sleep = _NoopSleep()
    transport = ResilientTransport(
        policy=HttpPolicy(max_attempts=3, backoff_max_seconds=60.0),
        inner=inner,
        sleep=sleep,
    )
    async with httpx.AsyncClient(transport=transport) as client:
        await client.get("https://example/api")
    # HTTP-date is approximate (network/system clock); allow a tolerance.
    assert len(sleep.delays) == 1
    assert 0.0 <= sleep.delays[0] <= 6.0


async def test_unparseable_retry_after_falls_back_to_backoff() -> None:
    inner = _seq_transport(
        [httpx.Response(429, headers={"Retry-After": "soon"}), httpx.Response(200)]
    )
    sleep = _NoopSleep()
    transport = ResilientTransport(
        policy=HttpPolicy(max_attempts=3, backoff_base_seconds=2.0),
        inner=inner,
        sleep=sleep,
        jitter=_no_jitter,
    )
    async with httpx.AsyncClient(transport=transport) as client:
        await client.get("https://example/api")
    # No Retry-After → computed backoff = base * 2^0 * jitter(1.0) = 2.0
    assert sleep.delays == [2.0]


# ---------------------------------------------------------------------------
# make_resilient_client factory
# ---------------------------------------------------------------------------


async def test_factory_returns_resilient_client() -> None:
    """The factory's client must retry transient failures like a hand-built one."""
    inner = _seq_transport([httpx.Response(503), httpx.Response(200)])
    async with make_resilient_client(
        policy=HttpPolicy(max_attempts=2, backoff_base_seconds=0.0, backoff_max_seconds=0.0),
        transport=inner,
    ) as client:
        response = await client.get("https://example/api")
    assert response.status_code == 200


async def test_factory_propagates_headers() -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers.get("authorization", "")
        return httpx.Response(200)

    async with make_resilient_client(
        headers={"Authorization": "Bearer token-123"},
        transport=httpx.MockTransport(handler),
    ) as client:
        await client.get("https://example/api")
    assert captured["authorization"] == "Bearer token-123"
