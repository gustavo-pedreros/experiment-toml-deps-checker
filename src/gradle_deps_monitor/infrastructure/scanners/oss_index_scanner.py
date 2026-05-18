"""OssIndexScanner — queries the Sonatype OSS Index for Maven CVEs."""

from __future__ import annotations

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

_API_URL = "https://ossindex.sonatype.org/api/v3/component-report"
_CACHE_PREFIX = "ossidx"
_DEFAULT_TTL = 86_400  # 24 hours
_BATCH_SIZE = 128  # max components per POST request

# Sentinel distinguishes cache miss from a cached empty list.
_MISS = object()


def _purl(lib: Library) -> str:
    """Return the Package URL for *lib* in Maven format.

    Example: ``pkg:maven/com.squareup.okhttp3/okhttp@4.9.1``
    """
    return f"pkg:maven/{lib.group}/{lib.artifact}@{lib.version}"


def _severity_from_cvss(score: float | None) -> AdvisorySeverity:
    """Map a CVSS v3 score to :class:`AdvisorySeverity`.

    Thresholds follow NVD / FIRST definitions:

    - CRITICAL ≥ 9.0
    - HIGH     ≥ 7.0
    - MEDIUM   ≥ 4.0
    - LOW      > 0
    - UNKNOWN  when score is ``None`` or ``0``
    """
    if score is None or score == 0:
        return AdvisorySeverity.UNKNOWN
    if score >= 9.0:
        return AdvisorySeverity.CRITICAL
    if score >= 7.0:
        return AdvisorySeverity.HIGH
    if score >= 4.0:
        return AdvisorySeverity.MEDIUM
    return AdvisorySeverity.LOW


class OssIndexScanner:
    """Fetches security advisories from the Sonatype OSS Index.

    Each library is identified by its Maven Package URL
    (``pkg:maven/{group}/{artifact}@{version}``).

    Uncached PURLs are sent in batches of up to :attr:`_BATCH_SIZE` per POST
    request.  Results are cached per PURL on disk for :attr:`_ttl` seconds
    (default: 24 h) so repeat scans of the same catalog version avoid the API.

    Authentication is optional but recommended for higher rate limits.

    :param username:  OSS Index account e-mail (``OSSINDEX_USER`` env var).
    :param api_key:   OSS Index API key (``OSSINDEX_API_KEY`` env var).
    :param cache_dir: Directory for the persistent disk cache.
    :param ttl:       Cache TTL in seconds.
    :param client:    Optional ``httpx.AsyncClient`` (caller manages lifetime).
                      When omitted, a new client is created per :meth:`scan` call.
    """

    def __init__(
        self,
        username: str | None = None,
        api_key: str | None = None,
        cache_dir: Path = Path(".cache/ossindex"),
        ttl: int = _DEFAULT_TTL,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._username = username
        self._api_key = api_key
        self._cache = diskcache.Cache(str(cache_dir))
        self._ttl = ttl
        self._client = client

    async def scan(self, libraries: tuple[Library, ...]) -> tuple[LibraryAdvisory, ...]:
        """Return advisories for every library in *libraries*.

        Libraries with no known advisories get an entry with an empty
        ``advisories`` tuple.

        :raises VulnerabilityScanError: On unrecoverable network or API error.
        """
        if self._client is not None:
            return await self._scan_with(self._client, libraries)

        # RFC-0030: resilient transport adds retry/backoff/Retry-After
        # honoring transparently. OSS Index batches sequentially in
        # ``_batch_fetch`` (line ~150), so no Semaphore is needed here.
        policy = HttpPolicy(timeout_seconds=30.0)
        async with make_resilient_client(policy=policy) as client:
            return await self._scan_with(client, libraries)

    async def _scan_with(
        self,
        client: httpx.AsyncClient,
        libraries: tuple[Library, ...],
    ) -> tuple[LibraryAdvisory, ...]:
        # 1. Resolve cache hits; collect uncached PURLs.
        advisory_map: dict[str, list[Advisory]] = {}
        uncached_purls: list[str] = []

        for lib in libraries:
            purl = _purl(lib)
            cached = self._cache.get(f"{_CACHE_PREFIX}:{purl}", default=_MISS)
            if cached is not _MISS:
                raw_list: list[dict[str, Any]] = cached
                advisory_map[purl] = _parse_component_vulns(raw_list)
            else:
                uncached_purls.append(purl)

        # 2. Batch-fetch uncached PURLs (up to _BATCH_SIZE per POST).
        if uncached_purls:
            fetched = await self._batch_fetch(client, uncached_purls)
            for purl, raw_list in fetched.items():
                self._cache.set(f"{_CACHE_PREFIX}:{purl}", raw_list, expire=self._ttl)
                advisory_map[purl] = _parse_component_vulns(raw_list)

        # 3. Build ordered results matching the input tuple.
        return tuple(
            LibraryAdvisory(
                alias=lib.alias,
                coordinate=f"{lib.group}:{lib.artifact}",
                version=str(lib.version),
                advisories=tuple(advisory_map.get(_purl(lib), [])),
            )
            for lib in libraries
        )

    async def _batch_fetch(
        self,
        client: httpx.AsyncClient,
        purls: list[str],
    ) -> dict[str, list[dict[str, Any]]]:
        """POST *purls* in batches and return a ``{purl: raw_vulns}`` map."""
        result: dict[str, list[dict[str, Any]]] = {}

        for i in range(0, len(purls), _BATCH_SIZE):
            batch = purls[i : i + _BATCH_SIZE]
            try:
                response = await client.post(
                    _API_URL,
                    json={"coordinates": batch},
                    headers=self._auth_headers(),
                )
            except httpx.RequestError as exc:
                raise VulnerabilityScanError(
                    f"Network error querying OSS Index for {batch[0]!r}: {exc}"
                ) from exc

            if not response.is_success:
                raise VulnerabilityScanError(f"OSS Index API returned HTTP {response.status_code}")

            for component in response.json():
                purl = component.get("coordinates", "")
                result[purl] = component.get("vulnerabilities", [])

        return result

    def _auth_headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if self._username and self._api_key:
            import base64

            token = base64.b64encode(f"{self._username}:{self._api_key}".encode()).decode()
            headers["Authorization"] = f"Basic {token}"
        return headers


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def _parse_component_vulns(raw_list: list[dict[str, Any]]) -> list[Advisory]:
    """Parse the ``vulnerabilities`` list from one OSS Index component report."""
    return [adv for raw in raw_list if (adv := _parse_vulnerability(raw)) is not None]


def _parse_vulnerability(raw: dict[str, Any]) -> Advisory | None:
    """Return an :class:`Advisory` from an OSS Index vulnerability dict, or ``None``.

    OSS Index vulnerability dicts include: ``id``, ``displayName``, ``title``,
    ``description``, ``cvssScore``, ``cvssVector``, ``cve``, ``cwe``,
    ``reference``, ``externalReferences``.
    """
    cve_id: str | None = raw.get("cve") or None
    oss_id: str = raw.get("id", "")
    if not oss_id and not cve_id:
        return None

    cvss_score: float | None = raw.get("cvssScore")
    severity = _severity_from_cvss(cvss_score)

    summary = raw.get("title") or raw.get("description") or ""
    url = raw.get("reference", "")

    return Advisory(
        # ghsa_id is the generic advisory-ID field; OSS Index uses its own ID scheme.
        ghsa_id=oss_id,
        cve_id=cve_id,
        severity=severity,
        summary=summary,
        fixed_version=None,  # OSS Index does not provide a fixed version
        url=url,
        source="oss_index",
    )
