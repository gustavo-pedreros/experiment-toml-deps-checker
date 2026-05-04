"""VersionRegistry port — outbound protocol for looking up artifact versions."""

from __future__ import annotations

from typing import Protocol

from gradle_deps_monitor.domain.version import MavenVersion


class VersionRegistryError(Exception):
    """Raised on unrecoverable registry failures (network error, bad XML, etc.).

    404 responses are NOT errors — they return ``None`` from :meth:`get_latest`.
    """


class VersionRegistry(Protocol):
    """Outbound port: look up the latest stable version of a Maven artifact."""

    async def get_latest(self, group: str, artifact: str) -> MavenVersion | None:
        """Return the latest stable version, or ``None`` if not found in this registry.

        :raises VersionRegistryError: On network failure or malformed response.
        """
        ...
