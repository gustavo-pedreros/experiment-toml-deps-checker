"""VersionStatusResolver port — high-level outbound protocol for RFC-0013.

The use case asks "what is the latest stable for every library in
this catalog?" The :class:`VersionStatusResolver` answers in one
call, so callers never have to know there are two backing registries
(Maven Central + Google Maven) or how routing decisions are made.

The lower-level :class:`VersionRegistry` port stays for cases that
need a single per-artifact lookup (e.g. tooling tests, scripts).
"""

from __future__ import annotations

from typing import Protocol

from gradle_deps_monitor.domain.catalog import Library
from gradle_deps_monitor.domain.version_status import LibraryVersionStatus


class VersionStatusResolver(Protocol):
    """Outbound port: produce a :class:`LibraryVersionStatus` per library."""

    async def resolve(self, libraries: tuple[Library, ...]) -> tuple[LibraryVersionStatus, ...]:
        """Return one status per library, preserving input order.

        Implementations MUST swallow per-artifact errors (network
        failures, malformed XML) and return ``UNKNOWN`` drift for the
        affected library — a single bad lookup must not abort the
        whole resolution.
        """
        ...
