"""GenerateFreezeReport — core use case (Phase 1)."""

from __future__ import annotations

from pathlib import Path

from gradle_deps_monitor.application.ports.catalog_parser import CatalogParser
from gradle_deps_monitor.application.ports.health_checker import HealthChecker
from gradle_deps_monitor.domain import FreezeReport


class GenerateFreezeReport:
    """Parse a Gradle Version Catalog and return a :class:`FreezeReport`.

    Dependencies are injected via the constructor so that tests can supply
    stub implementations without touching the filesystem or running rules.

    :param catalog_parser: Port implementation that reads a TOML file.
    :param health_checker: Optional callable that audits the parsed catalog.
        When omitted, ``health_findings`` will be empty in the report.
    """

    def __init__(
        self,
        catalog_parser: CatalogParser,
        health_checker: HealthChecker | None = None,
    ) -> None:
        self._parser = catalog_parser
        self._health_checker = health_checker

    def execute(self, catalog_path: Path) -> FreezeReport:
        """Parse *catalog_path* and return a :class:`~gradle_deps_monitor.domain.FreezeReport`.

        :param catalog_path: Path to the ``libs.versions.toml`` file, or to
            the directory that contains it.
        :raises CatalogParseError: Propagated from the parser on any I/O or
            format error.
        """
        catalog = self._parser.parse(catalog_path)
        findings = self._health_checker(catalog) if self._health_checker else ()
        return FreezeReport(catalog=catalog, health_findings=findings)
