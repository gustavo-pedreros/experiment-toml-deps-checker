"""FreezeReport — the aggregate root of the domain (ADR-0007)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from gradle_deps_monitor.domain.advisory import LibraryAdvisory
from gradle_deps_monitor.domain.bom import BomResolution
from gradle_deps_monitor.domain.catalog import Catalog
from gradle_deps_monitor.domain.changelog import BreakingSignal, ChangelogEntry, ChangelogFetchStats
from gradle_deps_monitor.domain.compliance import ComplianceFinding, ComplianceSeverity
from gradle_deps_monitor.domain.finding import Finding
from gradle_deps_monitor.domain.library_health import (
    HealthSignal,
    LibraryHealthFinding,
    LibraryHealthSeverity,
)
from gradle_deps_monitor.domain.license import LicenseAudit
from gradle_deps_monitor.domain.module_usage import ModuleUsageMap
from gradle_deps_monitor.domain.risk_score import RiskScoreReport
from gradle_deps_monitor.domain.toolchain import ToolchainFinding, ToolchainSeverity
from gradle_deps_monitor.domain.version_status import LibraryVersionStatus, VersionDrift


@dataclass(frozen=True)
class FreezeReport:
    """Snapshot of a Gradle catalog produced at a single point in time.

    This is the aggregate root. The ``GenerateFreezeReport`` use case
    (Phase 1, Step 4) is the only factory that constructs instances.

    Attributes added in later steps:
    - ``git_ref`` — the tag or commit SHA this report is anchored to
    """

    catalog: Catalog
    generated_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))
    health_findings: tuple[Finding, ...] = field(default_factory=tuple)
    security_advisories: tuple[LibraryAdvisory, ...] = field(default_factory=tuple)
    compliance_findings: tuple[ComplianceFinding, ...] = field(default_factory=tuple)
    toolchain_findings: tuple[ToolchainFinding, ...] = field(default_factory=tuple)
    library_health_findings: tuple[LibraryHealthFinding, ...] = field(default_factory=tuple)
    changelog_entries: tuple[ChangelogEntry, ...] = field(default_factory=tuple)
    changelog_stats: ChangelogFetchStats = field(default_factory=ChangelogFetchStats)
    module_usage_map: ModuleUsageMap | None = field(default=None)
    license_audit: LicenseAudit | None = field(default=None)
    risk_score_report: RiskScoreReport | None = field(default=None)
    library_version_statuses: tuple[LibraryVersionStatus, ...] = field(default_factory=tuple)
    bom_resolutions: tuple[BomResolution, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.generated_at.tzinfo is None:
            raise ValueError("generated_at must be timezone-aware")

    @property
    def vulnerable_libraries(self) -> tuple[LibraryAdvisory, ...]:
        """Libraries that have at least one active advisory."""
        return tuple(la for la in self.security_advisories if la.is_vulnerable)

    @property
    def has_critical_vulnerabilities(self) -> bool:
        """``True`` when any library has a CRITICAL advisory."""
        return any(la.has_critical for la in self.security_advisories)

    @property
    def has_high_vulnerabilities(self) -> bool:
        """``True`` when any library has a HIGH advisory."""
        return any(la.has_high for la in self.security_advisories)

    @property
    def has_compliance_violations(self) -> bool:
        """``True`` when any compliance finding is ERROR severity."""
        return any(f.severity == ComplianceSeverity.ERROR for f in self.compliance_findings)

    @property
    def has_compliance_warnings(self) -> bool:
        """``True`` when any compliance finding is WARNING severity."""
        return any(f.severity == ComplianceSeverity.WARNING for f in self.compliance_findings)

    @property
    def has_toolchain_errors(self) -> bool:
        """``True`` when any toolchain finding is ERROR severity."""
        return any(f.severity == ToolchainSeverity.ERROR for f in self.toolchain_findings)

    @property
    def has_toolchain_warnings(self) -> bool:
        """``True`` when any toolchain finding is WARNING severity."""
        return any(f.severity == ToolchainSeverity.WARNING for f in self.toolchain_findings)

    @property
    def deprecated_libraries(self) -> tuple[LibraryHealthFinding, ...]:
        """Findings from the curated KB or POM relocation signal."""
        return tuple(
            f
            for f in self.library_health_findings
            if f.signal in (HealthSignal.CURATED, HealthSignal.RELOCATED)
        )

    @property
    def inactive_libraries(self) -> tuple[LibraryHealthFinding, ...]:
        """Findings from the inactivity heuristic signal."""
        return tuple(f for f in self.library_health_findings if f.signal == HealthSignal.INACTIVE)

    @property
    def has_deprecated_libraries(self) -> bool:
        """``True`` when any library is flagged as deprecated or relocated."""
        return bool(self.deprecated_libraries)

    @property
    def has_high_health_findings(self) -> bool:
        """``True`` when any library health finding has HIGH severity."""
        return any(f.severity == LibraryHealthSeverity.HIGH for f in self.library_health_findings)

    @property
    def breaking_upgrades(self) -> tuple[ChangelogEntry, ...]:
        """Changelog entries where breaking changes are likely."""
        return tuple(
            e for e in self.changelog_entries if e.breaking_signal == BreakingSignal.LIKELY
        )

    @property
    def has_breaking_upgrades(self) -> bool:
        """``True`` when at least one major upgrade has breaking changes likely."""
        return bool(self.breaking_upgrades)

    @property
    def has_license_violations(self) -> bool:
        """``True`` when the license audit found any STRONG_COPYLEFT libraries."""
        return self.license_audit is not None and self.license_audit.has_violations

    @property
    def has_license_warnings(self) -> bool:
        """``True`` when the license audit found WEAK_COPYLEFT or UNKNOWN libraries."""
        return self.license_audit is not None and self.license_audit.has_warnings

    @property
    def outdated_libraries(self) -> tuple[LibraryVersionStatus, ...]:
        """Libraries whose pinned version is behind the latest stable.

        Excludes :attr:`VersionDrift.NONE` and :attr:`VersionDrift.UNKNOWN`.
        """
        return tuple(
            s
            for s in self.library_version_statuses
            if s.drift in (VersionDrift.PATCH, VersionDrift.MINOR, VersionDrift.MAJOR)
        )

    @property
    def major_outdated_count(self) -> int:
        """Number of libraries with major-version drift."""
        return sum(1 for s in self.library_version_statuses if s.drift == VersionDrift.MAJOR)

    @property
    def minor_outdated_count(self) -> int:
        """Number of libraries with minor-version drift."""
        return sum(1 for s in self.library_version_statuses if s.drift == VersionDrift.MINOR)

    @property
    def patch_outdated_count(self) -> int:
        """Number of libraries with patch-version drift."""
        return sum(1 for s in self.library_version_statuses if s.drift == VersionDrift.PATCH)
