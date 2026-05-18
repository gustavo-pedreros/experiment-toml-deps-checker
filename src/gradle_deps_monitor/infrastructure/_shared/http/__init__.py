"""Shared HTTP resilience layer (RFC-0030).

Owns retry policy, exponential backoff with jitter, ``Retry-After``
header honoring, rate-limit detection, timeout configuration. Adapters
opt in by constructing their :class:`httpx.AsyncClient` through
:func:`~gradle_deps_monitor.infrastructure._shared.http.client.make_resilient_client`
instead of calling ``httpx.AsyncClient(...)`` directly.

The resolution order for HTTP behaviour is:

1. Adapter-level constructor: each adapter picks its own
   :class:`HttpPolicy` instance (e.g. GHSA = 30 s timeout, Maven
   registries = 10 s).
2. ``HttpPolicy`` defaults: documented in :class:`HttpPolicy`.

PR1 introduces the package and adopts it in ``GitHubAdvisoryScanner``;
PR2 rolls out to OSS Index, the changelog fetcher, the Maven
registries, and the POM checkers; PR3 retires the per-adapter
``_HTTP_TIMEOUT`` constants.
"""

from gradle_deps_monitor.infrastructure._shared.http.client import make_resilient_client
from gradle_deps_monitor.infrastructure._shared.http.policy import HttpPolicy
from gradle_deps_monitor.infrastructure._shared.http.rate_limit import is_rate_limited
from gradle_deps_monitor.infrastructure._shared.http.transport import ResilientTransport

__all__ = [
    "HttpPolicy",
    "ResilientTransport",
    "is_rate_limited",
    "make_resilient_client",
]
