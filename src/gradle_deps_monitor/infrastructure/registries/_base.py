"""Shared base for Maven-metadata-XML registries (Template Method pattern)."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import ClassVar

import diskcache
import httpx

from gradle_deps_monitor.application.ports.version_registry import VersionRegistryError
from gradle_deps_monitor.domain.version import MavenVersion

# Sentinel distinguishes "key not in cache" from "cached value is falsy".
_MISS = object()


class MavenMetadataRegistry:
    """Fetches ``maven-metadata.xml`` from a Maven-compatible repository.

    Subclasses declare :attr:`_BASE_URL` and :attr:`_CACHE_PREFIX`; this
    class provides the full request / cache / parse pipeline.

    :param client: Shared ``httpx.AsyncClient`` (caller manages lifetime).
    :param cache_dir: Directory for the persistent disk cache.
    :param ttl: Cache TTL in seconds (default: 1 hour).
    """

    _BASE_URL: ClassVar[str]
    _CACHE_PREFIX: ClassVar[str]

    def __init__(
        self,
        client: httpx.AsyncClient,
        cache_dir: Path,
        ttl: int = 3600,
    ) -> None:
        self._client = client
        self._cache = diskcache.Cache(str(cache_dir))
        self._ttl = ttl

    async def get_latest(self, group: str, artifact: str) -> MavenVersion | None:
        """Return the latest stable release, or ``None`` if not listed.

        The result is cached on disk under *cache_dir* for :attr:`_ttl`
        seconds. RFC-0029 namespaces the cache key by outcome so 404
        negatives can be selectively purged from the positive entries:

        - Positive (resolved version) → ``{prefix}:ok:{group}:{artifact}``
        - Negative (404 from upstream) → ``{prefix}:404:{group}:{artifact}``

        :raises VersionRegistryError: On network failure or malformed XML.
        """
        positive_key = self._positive_key(group, artifact)
        negative_key = self._negative_key(group, artifact)

        cached = self._cache.get(positive_key, default=_MISS)
        if cached is not _MISS:
            return MavenVersion(cached)
        cached_negative = self._cache.get(negative_key, default=_MISS)
        if cached_negative is not _MISS:
            return None

        url = self._metadata_url(group, artifact)
        try:
            response = await self._client.get(url, follow_redirects=True)
        except httpx.RequestError as exc:
            raise VersionRegistryError(f"Network error fetching {url}: {exc}") from exc

        if response.status_code == 404:
            self._cache.set(negative_key, True, expire=self._ttl)
            return None

        if not response.is_success:
            raise VersionRegistryError(f"Unexpected HTTP {response.status_code} from {url}")

        version_str = _parse_release(response.text, group, artifact)
        if version_str:
            self._cache.set(positive_key, version_str, expire=self._ttl)
            return MavenVersion(version_str)
        # XML parsed but no stable version surfaced — treat as negative
        # so we don't re-fetch on every catalog scan.
        self._cache.set(negative_key, True, expire=self._ttl)
        return None

    def clear_negative_entries(self) -> int:
        """Purge cached 404 entries for this registry; return count removed.

        Internal API (RFC-0029) — not yet exposed via the CLI. Lets a
        future ``--clear-negatives`` flag selectively re-fetch artifacts
        that were 404 last run but may have recovered upstream, without
        invalidating valid version entries.
        """
        prefix = f"{self._CACHE_PREFIX}:404:"
        removed = 0
        for key in list(self._cache):
            if isinstance(key, str) and key.startswith(prefix):
                del self._cache[key]
                removed += 1
        return removed

    def _metadata_url(self, group: str, artifact: str) -> str:
        group_path = group.replace(".", "/")
        return f"{self._BASE_URL}/{group_path}/{artifact}/maven-metadata.xml"

    def _positive_key(self, group: str, artifact: str) -> str:
        return f"{self._CACHE_PREFIX}:ok:{group}:{artifact}"

    def _negative_key(self, group: str, artifact: str) -> str:
        return f"{self._CACHE_PREFIX}:404:{group}:{artifact}"


def _parse_release(xml_text: str, group: str, artifact: str) -> str | None:
    """Extract the latest stable version from Maven metadata XML.

    Trusts the publisher's ``<versioning><release>`` tag when it
    classifies as :attr:`~...domain.version.Stability.STABLE`. When
    the publisher tags a pre-release as ``<release>`` (live observed
    for ``com.google.protobuf:protoc`` where ``<release>`` was set
    to ``21.0-rc-1``), falls back to scanning
    ``<versioning><versions><version>`` in reverse document order
    for the most recent stable entry. Maven Central writes
    ``<version>`` entries in publishing order, so reverse iteration
    yields the most recently released stable artifact across all
    release lines maintained at the coordinate.

    Preserves today's behaviour for the edge cases where no stable
    is available: returns the original ``<release>`` tag (or
    ``None`` when also missing) rather than ``None`` outright, so
    libraries that only ever publish alpha/beta releases continue
    to surface a usable "latest" string instead of collapsing to
    drift = UNKNOWN. RFC-0027.
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise VersionRegistryError(f"XML parse error for {group}:{artifact}: {exc}") from exc

    release = root.findtext("versioning/release") or None
    if release and MavenVersion(release).is_stable:
        return release

    # Publisher tag missing or pre-release — scan versions list in
    # reverse document order for the latest stable entry.
    for v in reversed(root.findall("versioning/versions/version")):
        text = v.text
        if text and MavenVersion(text).is_stable:
            return text

    return release
