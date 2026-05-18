"""ResilientTransport — retry / backoff / Retry-After wrapping (RFC-0030).

A thin :class:`httpx.AsyncBaseTransport` wrapper that adds three
operational concerns to an inner transport (default:
:class:`httpx.AsyncHTTPTransport`):

- **Retry on transient failures**: network errors
  (:class:`httpx.RequestError`) and HTTP responses ``429`` / ``5xx``
  (except ``501``) are retried up to ``policy.max_attempts - 1`` more
  times.
- **Exponential backoff with full jitter**: between retries, the
  transport sleeps for
  ``random.uniform(0, min(policy.backoff_max_seconds, policy.backoff_base_seconds * 2**attempt))``.
  Full jitter spreads thundering-herd reconvergence.
- **``Retry-After`` honoring**: when the response carries a
  ``Retry-After`` header, that value (seconds, or HTTP-date) overrides
  the computed backoff for that single retry.

The transport is **stateless across requests** — concurrency capping
remains the caller's responsibility via :class:`asyncio.Semaphore`.
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import httpx

from gradle_deps_monitor.infrastructure._shared.http.policy import HttpPolicy

SleepFn = Callable[[float], Awaitable[None]]
JitterFn = Callable[[], float]

# Server-side errors that warrant a retry. 501 (Not Implemented) is
# deliberately excluded — retrying won't make an unimplemented
# endpoint exist.
_RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


class ResilientTransport(httpx.AsyncBaseTransport):
    """Wrap an inner transport with retry / backoff / Retry-After.

    :param policy: Operational tunables (see :class:`HttpPolicy`).
    :param inner: The transport to delegate to. Defaults to a fresh
        :class:`httpx.AsyncHTTPTransport`. Tests inject
        :class:`httpx.MockTransport` here.
    :param sleep: Async sleep function. Defaults to
        :func:`asyncio.sleep`. Tests inject a fast stub to avoid
        wall-clock waits.
    :param jitter: Callable returning a float in ``[0, 1)`` used to
        spread the retry window. Defaults to :func:`random.random`.
        Tests inject a deterministic stub.
    """

    def __init__(
        self,
        policy: HttpPolicy | None = None,
        inner: httpx.AsyncBaseTransport | None = None,
        sleep: SleepFn | None = None,
        jitter: JitterFn | None = None,
    ) -> None:
        self._policy = policy or HttpPolicy()
        self._inner = inner or httpx.AsyncHTTPTransport()
        self._sleep: SleepFn = sleep if sleep is not None else asyncio.sleep
        self._jitter: JitterFn = jitter if jitter is not None else random.random

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        for attempt in range(1, self._policy.max_attempts + 1):
            try:
                response = await self._inner.handle_async_request(request)
            except httpx.RequestError:
                if attempt == self._policy.max_attempts:
                    raise
                await self._sleep_backoff(attempt, retry_after=None)
                continue

            if response.status_code not in _RETRYABLE_STATUS_CODES:
                return response
            if attempt == self._policy.max_attempts:
                return response

            retry_after = _parse_retry_after(response.headers.get("retry-after"))
            # Per httpx contract, callers/transports must close responses
            # they are not returning — otherwise the inner connection
            # cannot be reused on the next attempt.
            await response.aclose()
            await self._sleep_backoff(attempt, retry_after=retry_after)

        # ``HttpPolicy.__post_init__`` enforces ``max_attempts >= 1``,
        # so the loop above always returns or raises on the final
        # attempt. The raise below is for mypy's exhaustiveness check.
        raise RuntimeError("ResilientTransport: retry loop exited without producing a response")

    async def aclose(self) -> None:
        await self._inner.aclose()

    async def _sleep_backoff(self, attempt: int, retry_after: float | None) -> None:
        if retry_after is not None:
            delay = min(retry_after, self._policy.backoff_max_seconds)
        else:
            ceiling = min(
                self._policy.backoff_max_seconds,
                self._policy.backoff_base_seconds * (2 ** (attempt - 1)),
            )
            delay = ceiling * self._jitter()
        await self._sleep(delay)


def _parse_retry_after(header: str | None) -> float | None:
    """Return the ``Retry-After`` value as seconds, or ``None`` when absent / unparseable.

    The header may be either an integer count of seconds (most common)
    or an HTTP-date per RFC 7231. Both forms are honoured; anything
    else is treated as missing so the computed exponential backoff
    applies instead.
    """
    if not header:
        return None
    header = header.strip()
    try:
        return max(0.0, float(header))
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(header)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    delta = (when - datetime.now(tz=UTC)).total_seconds()
    return max(0.0, delta)
