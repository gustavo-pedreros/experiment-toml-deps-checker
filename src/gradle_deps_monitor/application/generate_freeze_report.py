"""GenerateFreezeReport — core use case (Phase 1, parse-only)."""

from __future__ import annotations

from pathlib import Path

from gradle_deps_monitor.application.ports.catalog_parser import CatalogParser
from gradle_deps_monitor.domain import FreezeReport


class GenerateFreezeReport:
    """Parse a Gradle Version Catalog and return a :class:`FreezeReport`.

    This is the v1 (parse-only) implementation. Later steps will enrich
    the report with version-check results, CVE findings, and catalog health
    scores. Dependencies are injected via the constructor so that tests can
    supply a stub parser without touching the filesystem.
    """

    def __init__(self, catalog_parser: CatalogParser) -> None:
        self._parser = catalog_parser

    def execute(self, catalog_path: Path) -> FreezeReport:
        """Parse *catalog_path* and return a :class:`~gradle_deps_monitor.domain.FreezeReport`.

        :param catalog_path: Path to the ``libs.versions.toml`` file, or to
            the directory that contains it.
        :raises CatalogParseError: Propagated from the parser on any I/O or
            format error.
        """
        catalog = self._parser.parse(catalog_path)
        return FreezeReport(catalog=catalog)
