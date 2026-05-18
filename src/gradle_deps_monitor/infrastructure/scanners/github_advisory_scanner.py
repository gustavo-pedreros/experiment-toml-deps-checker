"""GitHubAdvisoryScanner — queries the GitHub Advisory Database for Maven CVEs."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any

import diskcache
import httpx

from gradle_deps_monitor.application.ports.vulnerability_scanner import VulnerabilityScanError
from gradle_deps_monitor.domain.advisory import (
    Advisory,
    AdvisorySeverity,
    LibraryAdvisory,
)
from gradle_deps_monitor.domain.catalog import Library
from gradle_deps_monitor.infrastructure._shared.http import HttpPolicy, make_resilient_client

_API_BASE = "https://api.github.com"
_ADVISORIES_URL = f"{_API_BASE}/advisories"
_ECOSYSTEM = "maven"
_CACHE_PREFIX = "ghsa"
_DEFAULT_TTL = 86_400  # 24 hours
_PER_PAGE = 100

# RFC-0024 PR #1: cap concurrent per-library requests during a scan.
# Authenticated GitHub API allows 5 000 req/h; 20 in-flight requests is
# a polite burst that amortises round-trip latency without risking
# secondary abuse limits. Unauthenticated 60 req/h is the bottleneck
# regardless of concurrency.
_MAX_CONCURRENT_REQUESTS = 20

# Sentinel distinguishes cache miss from a cached empty list.
_MISS = object()

# Pattern to parse version range components like "< 1.2.3" or ">= 1.0.0".
_RANGE_RE = re.compile(r"(>=|<=|>|<|=)\s*([\w.\-]+)")

_SEVERITY_MAP: dict[str, AdvisorySeverity] = {
    "critical": AdvisorySeverity.CRITICAL,
    "high": AdvisorySeverity.HIGH,
    "moderate": AdvisorySeverity.MEDIUM,
    "medium": AdvisorySeverity.MEDIUM,
    "low": AdvisorySeverity.LOW,
}


class GitHubAdvisoryScanner:
    """Fetches security advisories from the GitHub Advisory Database.

    Each library is queried by its Maven coordinate (``group:artifact``).
    Results are cached on disk for :attr:`_ttl` seconds (default: 24 h).

    :param token:     GitHub personal access token or ``GITHUB_TOKEN`` value.
                      Unauthenticated requests are limited to 60/hour.
    :param cache_dir: Directory for the persistent disk cache.
    :param ttl:       Cache TTL in seconds.
    :param client:    Optional ``httpx.AsyncClient`` (caller manages lifetime).
                      When omitted, a new client is created per :meth:`scan` call.
    """

    def __init__(
        self,
        token: str | None = None,
        cache_dir: Path = Path(".cache/ghsa"),
        ttl: int = _DEFAULT_TTL,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._token = token
        self._cache = diskcache.Cache(str(cache_dir))
        self._ttl = ttl
        self._client = client

    async def scan(self, libraries: tuple[Library, ...]) -> tuple[LibraryAdvisory, ...]:
        """Return advisories for every library in *libraries*.

        Libraries with no known advisories get an entry with an empty
        ``advisories`` tuple. The underlying ``httpx.AsyncClient`` is
        built by
        :func:`~gradle_deps_monitor.infrastructure._shared.http.make_resilient_client`
        (RFC-0030), so transient 429 / 5xx / network errors are
        retried with exponential backoff + jitter and ``Retry-After``
        is honored.

        :raises VulnerabilityScanError: On unrecoverable network or API error.
        """
        if self._client is not None:
            return await self._scan_with(self._client, libraries)

        policy = HttpPolicy(timeout_seconds=30.0, max_concurrency=_MAX_CONCURRENT_REQUESTS)
        async with make_resilient_client(policy=policy, headers=self._auth_headers()) as client:
            return await self._scan_with(client, libraries)

    async def _scan_with(
        self,
        client: httpx.AsyncClient,
        libraries: tuple[Library, ...],
    ) -> tuple[LibraryAdvisory, ...]:
        """Run per-library advisory lookups in parallel with bounded concurrency.

        RFC-0024 PR #1: pre-fix this loop ran serially, costing 30-50 s
        of wall-clock on a cold cache for typical Android catalogs
        (100-200 libs). ``asyncio.gather`` over per-library coroutines
        amortises round-trip latency; ``asyncio.Semaphore`` caps
        in-flight requests at :data:`_MAX_CONCURRENT_REQUESTS` to stay
        polite to GitHub's API. Output order matches input order
        because ``gather`` preserves submission order.
        """
        sem = asyncio.Semaphore(_MAX_CONCURRENT_REQUESTS)

        async def _one(lib: Library) -> LibraryAdvisory:
            async with sem:
                advisories = await self._advisories_for(client, lib)
            return LibraryAdvisory(
                alias=lib.alias,
                coordinate=f"{lib.group}:{lib.artifact}",
                version=str(lib.version),
                advisories=tuple(advisories),
            )

        return tuple(await asyncio.gather(*(_one(lib) for lib in libraries)))

    async def _advisories_for(
        self,
        client: httpx.AsyncClient,
        lib: Library,
    ) -> list[Advisory]:
        package_name = f"{lib.group}:{lib.artifact}"
        cache_key = f"{_CACHE_PREFIX}:{package_name}"

        cached = self._cache.get(cache_key, default=_MISS)
        if cached is not _MISS:
            raw_list: list[dict[str, Any]] = cached
        else:
            raw_list = await self._fetch_advisories(client, package_name)
            self._cache.set(cache_key, raw_list, expire=self._ttl)

        version = str(lib.version)
        return [
            adv
            for raw in raw_list
            if (adv := _parse_advisory(raw, package_name, version)) is not None
        ]

    async def _fetch_advisories(
        self,
        client: httpx.AsyncClient,
        package_name: str,
    ) -> list[dict[str, Any]]:
        """Fetch all advisories for *package_name* from the GitHub API (paginated)."""
        params: dict[str, str | int] = {
            "ecosystem": _ECOSYSTEM,
            "affects": package_name,
            "per_page": _PER_PAGE,
        }
        all_items: list[dict[str, Any]] = []
        url: str | None = _ADVISORIES_URL

        while url:
            try:
                response = await client.get(url, params=params)
            except httpx.RequestError as exc:
                raise VulnerabilityScanError(
                    f"Network error querying GitHub Advisory DB for {package_name}: {exc}"
                ) from exc

            if response.status_code == 404:
                break

            if not response.is_success:
                raise VulnerabilityScanError(
                    f"GitHub Advisory API returned HTTP {response.status_code} for {package_name}"
                )

            all_items.extend(response.json())

            # Follow the Link header for pagination (only on first request).
            url = _next_page_url(response)
            params = {}  # subsequent requests use the full URL from Link header

        return all_items

    def _auth_headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def _parse_advisory(
    raw: dict[str, Any],
    package_name: str,
    version: str,
) -> Advisory | None:
    """Return an :class:`Advisory` if *version* is in the affected range, else ``None``."""
    vulnerabilities: list[dict[str, Any]] = raw.get("vulnerabilities", [])

    affected_range: str | None = None
    fixed_version: str | None = None

    for vuln in vulnerabilities:
        pkg = vuln.get("package", {})
        if pkg.get("ecosystem", "").lower() != _ECOSYSTEM:
            continue
        if pkg.get("name", "") != package_name:
            continue
        affected_range = vuln.get("vulnerable_version_range")
        fixed_version = vuln.get("first_patched_version")
        break
    else:
        # No matching package entry in this advisory.
        return None

    if not _version_in_range(version, affected_range, fixed_version):
        return None

    severity_raw = raw.get("severity", "unknown").lower()
    severity = _SEVERITY_MAP.get(severity_raw, AdvisorySeverity.UNKNOWN)

    return Advisory(
        ghsa_id=raw.get("ghsa_id", ""),
        cve_id=raw.get("cve_id") or None,
        severity=severity,
        summary=raw.get("summary", ""),
        fixed_version=fixed_version or None,
        url=raw.get("html_url", ""),
        source="github",
    )


def _version_in_range(
    version: str,
    vulnerable_range: str | None,
    fixed_version: str | None,
) -> bool:
    """Return ``True`` if *version* falls within the vulnerable range.

    Strategy (conservative):
    1. If ``fixed_version`` is known and *version* < ``fixed_version`` → affected.
    2. Otherwise, attempt to parse ``vulnerable_range`` and evaluate.
    3. If neither is available → assume affected (surface the advisory).
    """
    if fixed_version:
        try:
            # version < fixed_version → affected; version >= fixed_version → patched.
            return _version_lt(version, fixed_version)
        except ValueError:
            pass  # fall through to range parsing

    if vulnerable_range:
        return _evaluate_range(version, vulnerable_range)

    # No version information available — surface conservatively.
    return True


def _evaluate_range(version: str, version_range: str) -> bool:
    """Evaluate whether *version* satisfies all clauses in *version_range*.

    A range is a comma-separated list of clauses like ``">= 1.0.0, < 1.5.0"``.
    Returns ``True`` if the version satisfies ALL clauses (i.e. is in the range).
    """
    clauses = [c.strip() for c in version_range.split(",")]
    for clause in clauses:
        m = _RANGE_RE.match(clause)
        if not m:
            continue
        op, bound = m.group(1), m.group(2)
        try:
            result = _compare_op(op, version, bound)
        except ValueError:
            continue
        if not result:
            return False
    return True


def _compare_op(op: str, version: str, bound: str) -> bool:
    """Return whether ``version <op> bound`` is true."""
    lt = _version_lt(version, bound)
    eq = _version_eq(version, bound)
    if op == "<":
        return lt
    if op == "<=":
        return lt or eq
    if op == ">":
        return not lt and not eq
    if op == ">=":
        return not lt
    if op == "=":
        return eq
    return False


def _version_parts(version: str) -> tuple[int, ...]:
    """Extract numeric parts from a version string (e.g. ``"1.2.3"`` → ``(1, 2, 3)``)."""
    parts = re.split(r"[.\-]", version)
    result: list[int] = []
    for part in parts:
        if part.isdigit():
            result.append(int(part))
        else:
            break  # stop at first non-numeric component (e.g. "-alpha01")
    if not result:
        raise ValueError(f"Cannot parse version: {version!r}")
    return tuple(result)


def _version_lt(a: str, b: str) -> bool:
    """Return ``True`` if version *a* is strictly less than *b*."""
    pa, pb = _version_parts(a), _version_parts(b)
    # Pad to same length.
    length = max(len(pa), len(pb))
    pa = pa + (0,) * (length - len(pa))
    pb = pb + (0,) * (length - len(pb))
    return pa < pb


def _version_eq(a: str, b: str) -> bool:
    """Return ``True`` if the numeric parts of *a* and *b* are equal."""
    try:
        return _version_parts(a) == _version_parts(b)
    except ValueError:
        return a == b


def _next_page_url(response: httpx.Response) -> str | None:
    """Extract the ``next`` page URL from the ``Link`` header, if present."""
    link_header = response.headers.get("link", "")
    for part in link_header.split(","):
        part = part.strip()
        if 'rel="next"' in part:
            match = re.search(r"<([^>]+)>", part)
            if match:
                return match.group(1)
    return None
