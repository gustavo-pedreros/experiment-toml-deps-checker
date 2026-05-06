"""MavenVersionStatusResolver — wires the two registry adapters (RFC-0013).

For each library the resolver:

1. Picks the *primary* registry based on the group prefix
   (``androidx.*`` and ``com.google.*`` go to Google Maven first; all
   other groups go to Maven Central first).
2. Falls back to the *secondary* registry on a 404 from the primary.
3. Wraps any per-artifact error into a fallback :attr:`VersionDrift.UNKNOWN`
   so a single failure does not abort the run.

This module owns the lifetime of the shared :class:`httpx.AsyncClient`,
keeping the use case layer free of HTTP details.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import httpx

from gradle_deps_monitor.application.ports.version_registry import VersionRegistryError
from gradle_deps_monitor.domain.catalog import Library
from gradle_deps_monitor.domain.version import MavenVersion
from gradle_deps_monitor.domain.version_status import (
    LibraryVersionStatus,
    VersionDrift,
    compute_drift,
)
from gradle_deps_monitor.infrastructure.registries._base import MavenMetadataRegistry
from gradle_deps_monitor.infrastructure.registries.google_maven import GoogleMavenRegistry
from gradle_deps_monitor.infrastructure.registries.maven_central import MavenCentralRegistry

_HTTP_TIMEOUT = httpx.Timeout(10.0)

# Group prefixes that are first-class on Google Maven. Hits to Maven
# Central for these groups will frequently 404, so trying Google first
# saves a round-trip on the common case.
_GOOGLE_PREFIXES: tuple[str, ...] = ("androidx.", "com.google.", "com.android.")


class MavenVersionStatusResolver:
    """Concrete :class:`~...application.ports.version_status_resolver.VersionStatusResolver`.

    :param cache_dir: Directory for the on-disk maven-metadata.xml cache.
    :param ttl: Cache TTL in seconds. Defaults to 1 h, matching the
        existing ``MavenMetadataRegistry`` default.
    """

    def __init__(self, cache_dir: Path, ttl: int = 3600) -> None:
        self._cache_dir = cache_dir
        self._ttl = ttl

    async def resolve(
        self,
        libraries: tuple[Library, ...],
    ) -> tuple[LibraryVersionStatus, ...]:
        """Return one :class:`LibraryVersionStatus` per library, in order."""
        if not libraries:
            return ()

        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            mc = MavenCentralRegistry(client, self._cache_dir, self._ttl)
            gm = GoogleMavenRegistry(client, self._cache_dir, self._ttl)
            tasks = [self._resolve_one(lib, mc, gm) for lib in libraries]
            statuses = await asyncio.gather(*tasks)
        return tuple(statuses)

    # ------------------------------------------------------------------
    # Per-library resolution
    # ------------------------------------------------------------------

    async def _resolve_one(
        self,
        lib: Library,
        mc: MavenMetadataRegistry,
        gm: MavenMetadataRegistry,
    ) -> LibraryVersionStatus:
        primary, secondary = self._choose(lib.group, mc, gm)
        latest: MavenVersion | None = None

        try:
            latest = await primary.get_latest(lib.group, lib.artifact)
        except VersionRegistryError:
            latest = None

        if latest is None:
            try:
                latest = await secondary.get_latest(lib.group, lib.artifact)
            except VersionRegistryError:
                latest = None

        return LibraryVersionStatus(
            alias=lib.alias,
            coordinate=f"{lib.group}:{lib.artifact}",
            pinned=lib.version,
            latest=latest,
            drift=compute_drift(lib.version, latest) if latest else VersionDrift.UNKNOWN,
        )

    @staticmethod
    def _choose(
        group: str,
        mc: MavenMetadataRegistry,
        gm: MavenMetadataRegistry,
    ) -> tuple[MavenMetadataRegistry, MavenMetadataRegistry]:
        """Return ``(primary, secondary)`` registries for *group*."""
        if any(group == p.rstrip(".") or group.startswith(p) for p in _GOOGLE_PREFIXES):
            return gm, mc
        return mc, gm
