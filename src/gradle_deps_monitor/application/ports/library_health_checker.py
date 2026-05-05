"""Port — library health checker protocol."""

from __future__ import annotations

from typing import Protocol

from gradle_deps_monitor.domain.catalog import Library
from gradle_deps_monitor.domain.library_health import LibraryHealthFinding


class LibraryHealthChecker(Protocol):
    """Checks a set of libraries for deprecation, relocation, and inactivity."""

    async def check(self, libraries: tuple[Library, ...]) -> tuple[LibraryHealthFinding, ...]:
        """Return health findings for *libraries*.

        Implementations combine up to three signals:
        - Curated knowledge base (bundled YAML)
        - Maven POM ``<relocation>`` tags (HTTP)
        - Inactivity heuristic via ``maven-metadata.xml`` (HTTP)
        """
        ...
