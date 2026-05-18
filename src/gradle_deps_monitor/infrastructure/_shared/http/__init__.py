"""Shared HTTP resilience layer (RFC-0030).

Owns retry policy, exponential backoff with jitter, ``Retry-After``
header honoring, rate-limit detection, timeout configuration. Adapters
opt in by constructing their :class:`httpx.AsyncClient` through
:func:`~gradle_deps_monitor.infrastructure._shared.http.client.make_resilient_client`
instead of calling ``httpx.AsyncClient(...)`` directly.

The resolution order for HTTP behaviour is:

1. **Adapter-level call site**: each adapter picks its own
   :class:`HttpPolicy` instance at the point where it constructs the
   client. Adapters that hit Maven Central from the freeze use case
   share a 10 s timeout; adapters that hit GitHub or POMs share 15 s;
   the vulnerability scanners use 30 s for their longer-running
   advisory queries.
2. :class:`HttpPolicy` **defaults**: the conservative fallback for
   any caller that doesn't override (30 s timeout, 3 attempts,
   1 s base / 30 s max backoff, 20 max concurrency).

Per-adapter rationale lives in the :class:`HttpPolicy` docstring;
this module's job is wiring, not policy curation.

All seven outbound HTTP adapters route through this layer:

- :class:`...scanners.github_advisory_scanner.GitHubAdvisoryScanner`
- :class:`...scanners.oss_index_scanner.OssIndexScanner`
- :class:`...fetchers.changelog_fetcher.ChangelogFetcher`
- :class:`...resolvers.maven_version_status_resolver.MavenVersionStatusResolver`
  (which builds both ``MavenCentralRegistry`` and ``GoogleMavenRegistry``)
- :class:`...resolvers.maven_bom_resolver.MavenBomResolver`
- :class:`...checkers.pom_license_checker.PomLicenseChecker`
- :class:`...checkers.library_health_checker.LibraryHealthChecker`
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
