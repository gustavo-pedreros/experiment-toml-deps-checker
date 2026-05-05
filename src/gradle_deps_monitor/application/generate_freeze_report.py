"""GenerateFreezeReport — core use case (Phase 1)."""

from __future__ import annotations

import asyncio
from pathlib import Path

from gradle_deps_monitor.application.ports.catalog_parser import CatalogParser
from gradle_deps_monitor.application.ports.changelog_fetcher import ChangelogFetcher
from gradle_deps_monitor.application.ports.compliance_checker import ComplianceChecker
from gradle_deps_monitor.application.ports.health_checker import HealthChecker
from gradle_deps_monitor.application.ports.library_health_checker import LibraryHealthChecker
from gradle_deps_monitor.application.ports.module_usage_scanner import ModuleUsageScanner
from gradle_deps_monitor.application.ports.toolchain_checker import ToolchainChecker
from gradle_deps_monitor.application.ports.vulnerability_scanner import VulnerabilityScanner
from gradle_deps_monitor.domain import FreezeReport
from gradle_deps_monitor.domain.advisory import LibraryAdvisory
from gradle_deps_monitor.domain.changelog import ChangelogEntry
from gradle_deps_monitor.domain.compliance import ComplianceFinding
from gradle_deps_monitor.domain.library_health import LibraryHealthFinding
from gradle_deps_monitor.domain.module_usage import ModuleUsageMap
from gradle_deps_monitor.domain.toolchain import ToolchainFinding


class GenerateFreezeReport:
    """Parse a Gradle Version Catalog and return a :class:`FreezeReport`.

    Dependencies are injected via the constructor so that tests can supply
    stub implementations without touching the filesystem or running rules.

    :param catalog_parser:       Port implementation that reads a TOML file.
    :param health_checker:       Optional callable that audits the parsed catalog.
                                 When omitted, ``health_findings`` will be empty.
    :param vulnerability_scanner: Optional scanner that queries security advisory
                                 databases.  When omitted (or when ``GITHUB_TOKEN``
                                 is not set), ``security_advisories`` will be empty.
    """

    def __init__(
        self,
        catalog_parser: CatalogParser,
        health_checker: HealthChecker | None = None,
        vulnerability_scanner: VulnerabilityScanner | None = None,
        compliance_checker: ComplianceChecker | None = None,
        toolchain_checker: ToolchainChecker | None = None,
        library_health_checker: LibraryHealthChecker | None = None,
        changelog_fetcher: ChangelogFetcher | None = None,
        module_usage_scanner: ModuleUsageScanner | None = None,
    ) -> None:
        self._parser = catalog_parser
        self._health_checker = health_checker
        self._scanner = vulnerability_scanner
        self._compliance_checker = compliance_checker
        self._toolchain_checker = toolchain_checker
        self._library_health_checker = library_health_checker
        self._changelog_fetcher = changelog_fetcher
        self._module_usage_scanner = module_usage_scanner

    def execute(self, catalog_path: Path) -> FreezeReport:
        """Parse *catalog_path* and return a :class:`~gradle_deps_monitor.domain.FreezeReport`.

        :param catalog_path: Path to the ``libs.versions.toml`` file, or to
            the directory that contains it.
        :raises CatalogParseError: Propagated from the parser on any I/O or
            format error.
        :raises VulnerabilityScanError: Propagated from the scanner on any
            unrecoverable network or API error.
        """
        catalog = self._parser.parse(catalog_path)
        findings = self._health_checker(catalog) if self._health_checker else ()

        security_advisories: tuple[LibraryAdvisory, ...] = ()
        if self._scanner is not None:
            libraries = tuple(catalog.libraries)
            security_advisories = asyncio.run(self._scanner.scan(libraries))

        compliance_findings: tuple[ComplianceFinding, ...] = ()
        if self._compliance_checker is not None:
            compliance_findings = self._compliance_checker.check(catalog)

        toolchain_findings: tuple[ToolchainFinding, ...] = ()
        if self._toolchain_checker is not None:
            toolchain_findings = self._toolchain_checker.check(catalog)

        library_health_findings: tuple[LibraryHealthFinding, ...] = ()
        if self._library_health_checker is not None:
            libraries = tuple(catalog.libraries)
            library_health_findings = asyncio.run(self._library_health_checker.check(libraries))

        changelog_entries: tuple[ChangelogEntry, ...] = ()
        if self._changelog_fetcher is not None:
            libraries = tuple(catalog.libraries)
            changelog_entries = asyncio.run(self._changelog_fetcher.fetch(libraries))

        module_usage_map: ModuleUsageMap | None = None
        if self._module_usage_scanner is not None:
            module_usage_map = self._module_usage_scanner.scan(catalog_path, catalog)

        return FreezeReport(
            catalog=catalog,
            health_findings=findings,
            security_advisories=security_advisories,
            compliance_findings=compliance_findings,
            toolchain_findings=toolchain_findings,
            library_health_findings=library_health_findings,
            changelog_entries=changelog_entries,
            module_usage_map=module_usage_map,
        )
