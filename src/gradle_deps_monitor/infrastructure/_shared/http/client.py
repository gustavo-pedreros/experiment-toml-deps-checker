"""Factory for resilient ``httpx.AsyncClient`` instances (RFC-0030)."""

from __future__ import annotations

import httpx

from gradle_deps_monitor.infrastructure._shared.http.policy import HttpPolicy
from gradle_deps_monitor.infrastructure._shared.http.transport import ResilientTransport


def make_resilient_client(
    *,
    policy: HttpPolicy | None = None,
    headers: dict[str, str] | None = None,
    follow_redirects: bool = False,
    transport: httpx.AsyncBaseTransport | None = None,
) -> httpx.AsyncClient:
    """Return an :class:`httpx.AsyncClient` wrapping a :class:`ResilientTransport`.

    :param policy: Operational tunables. Defaults to a built-in
        :class:`HttpPolicy` (30 s timeout, 3 attempts).
    :param headers: Optional default headers applied to every request
        the client issues. Adapters pass their auth headers here.
    :param follow_redirects: Whether the underlying client should
        transparently follow ``3xx`` responses. Matches the existing
        ``httpx.AsyncClient(follow_redirects=...)`` semantics.
    :param transport: Inner transport for the :class:`ResilientTransport`
        to delegate to. Tests pass an :class:`httpx.MockTransport` here.
        When omitted, the resilient transport falls back to its default
        :class:`httpx.AsyncHTTPTransport`.
    """
    pol = policy or HttpPolicy()
    resilient = ResilientTransport(policy=pol, inner=transport)
    return httpx.AsyncClient(
        transport=resilient,
        timeout=pol.timeout_seconds,
        headers=headers or {},
        follow_redirects=follow_redirects,
    )
