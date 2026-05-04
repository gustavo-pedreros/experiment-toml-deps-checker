"""CatalogParser port — outbound protocol for reading a version catalog."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from gradle_deps_monitor.domain import Catalog


class CatalogParseError(Exception):
    """Raised when a ``libs.versions.toml`` file cannot be parsed into a Catalog.

    Defined at the application/ports boundary so that callers (use cases,
    presentation) can catch it without depending on infrastructure.
    """


class CatalogParser(Protocol):
    """Outbound port: read a Gradle Version Catalog file into a :class:`Catalog`."""

    def parse(self, path: Path) -> Catalog:
        """Parse the TOML file at *path* and return the resulting :class:`Catalog`.

        :param path: Absolute path to a ``libs.versions.toml`` file.
        :raises CatalogParseError: If the file is missing, malformed, or
            contains unresolvable ``version.ref`` entries.
        """
        ...
