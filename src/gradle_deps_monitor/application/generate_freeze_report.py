"""GenerateFreezeReport — core use case (Phase 1).

Concurrency model
-----------------
RFC-0019 PR #3 moved this use case from "sync ``execute`` with seven
internal ``asyncio.run`` calls" to a single async ``execute``. The CLI
entry point now wraps the whole pipeline in one ``asyncio.run`` at the
outermost layer, matching the convention every other async port in the
project already follows.

RFC-0025 then turned the orchestration itself parallel. The use case
runs in three explicit phases:

1. **Phase 0 — sequential prelude.** Catalog parsing, BoM resolution
   + enrichment, and the cheap synchronous checks (health,
   compliance, toolchain). Every downstream adapter reads the
   enriched catalog, so this phase must complete first.
2. **Phase 1 — parallel fan-out.** The six adapters that consume the
   enriched catalog independently (vulnerability scanner, library
   health checker, changelog fetcher, module-usage scanner, license
   checker, version-status resolver) run concurrently via
   ``asyncio.gather``. Each adapter is itself internally parallel
   (its own ``gather`` over the library set), so the fan-out here
   sums per-stage costs into a single wall-clock dominated by the
   slowest adapter rather than ``sum(t_i)``.
3. **Phase 2 — sequential consumer.** Risk score depends on every
   Phase 1 output and must come last.

Empirically: a 170-library catalog with a valid ``GITHUB_TOKEN`` on a
cold cache dropped from 12.5 s (post-RFC-0024 PR #1, pre-RFC-0025) to
single-digit seconds after this refactor — the floor is the slowest
individual Phase 1 adapter. No port signature, domain model, or
schema changes; pure orchestration.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from gradle_deps_monitor.application.bom_enrichment import enrich_catalog_with_boms
from gradle_deps_monitor.application.compute_risk_score import score_libraries
from gradle_deps_monitor.application.ports.bom_resolver import BomResolver
from gradle_deps_monitor.application.ports.catalog_parser import CatalogParser
from gradle_deps_monitor.application.ports.changelog_fetcher import ChangelogFetcher
from gradle_deps_monitor.application.ports.compliance_checker import ComplianceChecker
from gradle_deps_monitor.application.ports.health_checker import HealthChecker
from gradle_deps_monitor.application.ports.library_health_checker import LibraryHealthChecker
from gradle_deps_monitor.application.ports.license_checker import LicenseChecker
from gradle_deps_monitor.application.ports.module_usage_scanner import ModuleUsageScanner
from gradle_deps_monitor.application.ports.toolchain_checker import ToolchainChecker
from gradle_deps_monitor.application.ports.version_status_resolver import VersionStatusResolver
from gradle_deps_monitor.application.ports.vulnerability_scanner import VulnerabilityScanner
from gradle_deps_monitor.domain import Catalog, FreezeReport, Library
from gradle_deps_monitor.domain.advisory import LibraryAdvisory
from gradle_deps_monitor.domain.bom import BomResolution
from gradle_deps_monitor.domain.changelog import ChangelogEntry, ChangelogFetchStats
from gradle_deps_monitor.domain.compliance import ComplianceFinding
from gradle_deps_monitor.domain.library_health import LibraryHealthFinding
from gradle_deps_monitor.domain.license import LicenseAudit
from gradle_deps_monitor.domain.module_usage import ModuleUsageMap
from gradle_deps_monitor.domain.risk_score import RiskScoreReport, RiskThresholds, RiskWeights
from gradle_deps_monitor.domain.toolchain import ToolchainFinding
from gradle_deps_monitor.domain.version_status import LibraryVersionStatus


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
        license_checker: LicenseChecker | None = None,
        version_status_resolver: VersionStatusResolver | None = None,
        bom_resolver: BomResolver | None = None,
        enable_risk_score: bool = False,
        risk_weights: RiskWeights | None = None,
        risk_thresholds: RiskThresholds | None = None,
    ) -> None:
        self._parser = catalog_parser
        self._health_checker = health_checker
        self._scanner = vulnerability_scanner
        self._compliance_checker = compliance_checker
        self._toolchain_checker = toolchain_checker
        self._library_health_checker = library_health_checker
        self._changelog_fetcher = changelog_fetcher
        self._module_usage_scanner = module_usage_scanner
        self._license_checker = license_checker
        self._version_status_resolver = version_status_resolver
        self._bom_resolver = bom_resolver
        self._enable_risk_score = enable_risk_score
        self._risk_weights = risk_weights
        self._risk_thresholds = risk_thresholds

    async def execute(self, catalog_path: Path) -> FreezeReport:
        """Parse *catalog_path* and return a :class:`~gradle_deps_monitor.domain.FreezeReport`.

        :param catalog_path: Path to the ``libs.versions.toml`` file, or to
            the directory that contains it.
        :raises CatalogParseError: Propagated from the parser on any I/O or
            format error.
        :raises VulnerabilityScanError: Propagated from the scanner on any
            unrecoverable network or API error.

        Coroutine: the caller is responsible for the event loop. The
        CLI does this with a single ``asyncio.run`` at its entry point;
        tests do the same. See the module docstring for the rationale.
        """
        # --- Phase 0 — sequential prelude ----------------------------------
        catalog = self._parser.parse(catalog_path)

        # BoM resolution must finish before downstream adapters see the
        # enriched catalog. Anything that reads ``catalog.libraries``
        # afterwards observes the resolved, member-included set.
        bom_resolutions: tuple[BomResolution, ...] = ()
        if self._bom_resolver is not None:
            bom_libraries = tuple(lib for lib in catalog.libraries if lib.is_bom_candidate)
            if bom_libraries:
                bom_resolutions = await self._bom_resolver.resolve(bom_libraries)
                catalog = enrich_catalog_with_boms(catalog, bom_resolutions)

        # Synchronous checks — microsecond-cost; keeping them in Phase 0
        # is simpler and faster than wrapping them in ``asyncio.to_thread``.
        findings = self._health_checker(catalog) if self._health_checker else ()
        compliance_findings: tuple[ComplianceFinding, ...] = (
            self._compliance_checker.check(catalog) if self._compliance_checker else ()
        )
        toolchain_findings: tuple[ToolchainFinding, ...] = (
            self._toolchain_checker.check(catalog) if self._toolchain_checker else ()
        )

        # --- Phase 1 — parallel fan-out -----------------------------------
        # Every adapter below is internally parallel (its own
        # ``asyncio.gather`` over the library set). Awaiting them at the
        # orchestration level via a single ``gather`` collapses the
        # per-stage wall-clocks into ``max(t_i)`` rather than ``sum(t_i)``.
        libraries = tuple(catalog.libraries)
        (
            security_advisories,
            library_health_findings,
            (changelog_entries, changelog_stats),
            module_usage_map,
            license_audit,
            library_version_statuses,
        ) = await asyncio.gather(
            self._safe_scan(libraries),
            self._safe_library_health(libraries),
            self._safe_changelog(libraries),
            self._safe_module_usage(catalog_path, catalog),
            self._safe_license(libraries),
            self._safe_version_status(libraries),
        )

        # RFC-0019 PR #1 contract: scanner-emitted findings (e.g. MOD-001
        # for unreadable build files) get appended to the existing
        # health-findings channel. This merge happens after the fan-out
        # because it consumes the scanner's output.
        if module_usage_map is not None and module_usage_map.findings:
            findings = findings + module_usage_map.findings

        # --- Phase 2 — sequential consumer --------------------------------
        # Risk score depends on every Phase 1 output; running it
        # concurrently is impossible by data dependency.
        risk_score_report: RiskScoreReport | None = None
        if self._enable_risk_score:
            risk_score_report = score_libraries(
                libraries=tuple(catalog.libraries),
                changelog_entries=changelog_entries,
                security_advisories=security_advisories,
                library_health_findings=library_health_findings,
                module_usage_map=module_usage_map,
                license_audit=license_audit,
                version_statuses=library_version_statuses,
                compliance_findings=compliance_findings,
                weights=self._risk_weights,
                thresholds=self._risk_thresholds,
            )

        return FreezeReport(
            catalog=catalog,
            health_findings=findings,
            security_advisories=security_advisories,
            compliance_findings=compliance_findings,
            toolchain_findings=toolchain_findings,
            library_health_findings=library_health_findings,
            changelog_entries=changelog_entries,
            changelog_stats=changelog_stats,
            module_usage_map=module_usage_map,
            license_audit=license_audit,
            risk_score_report=risk_score_report,
            library_version_statuses=library_version_statuses,
            bom_resolutions=bom_resolutions,
            # RFC-0028: authoritative "scanner was injected" signal,
            # consumed by writers to differentiate "scan not configured"
            # from "scanned, no advisories" when rendering the Security
            # section placeholder. Set from adapter presence at
            # construction time so a degenerate empty-catalog run with
            # a real scanner is still reported as scanned.
            security_scanned=self._scanner is not None,
        )

    # ------------------------------------------------------------------
    # Phase 1 wrappers — keep the ``gather`` call site free of None checks
    # ------------------------------------------------------------------

    async def _safe_scan(self, libraries: tuple[Library, ...]) -> tuple[LibraryAdvisory, ...]:
        if self._scanner is None:
            return ()
        return await self._scanner.scan(libraries)

    async def _safe_library_health(
        self, libraries: tuple[Library, ...]
    ) -> tuple[LibraryHealthFinding, ...]:
        if self._library_health_checker is None:
            return ()
        return await self._library_health_checker.check(libraries)

    async def _safe_changelog(
        self, libraries: tuple[Library, ...]
    ) -> tuple[tuple[ChangelogEntry, ...], ChangelogFetchStats]:
        if self._changelog_fetcher is None:
            return (), ChangelogFetchStats()
        return await self._changelog_fetcher.fetch(libraries)

    async def _safe_module_usage(
        self, catalog_path: Path, catalog: Catalog
    ) -> ModuleUsageMap | None:
        if self._module_usage_scanner is None:
            return None
        return await self._module_usage_scanner.scan(catalog_path, catalog)

    async def _safe_license(self, libraries: tuple[Library, ...]) -> LicenseAudit | None:
        if self._license_checker is None:
            return None
        return await self._license_checker.check(libraries)

    async def _safe_version_status(
        self, libraries: tuple[Library, ...]
    ) -> tuple[LibraryVersionStatus, ...]:
        if self._version_status_resolver is None:
            return ()
        return await self._version_status_resolver.resolve(libraries)
