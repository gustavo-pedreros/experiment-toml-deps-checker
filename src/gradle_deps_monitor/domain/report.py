"""FreezeReport — the aggregate root of the domain (ADR-0007)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from gradle_deps_monitor.domain.advisory import LibraryAdvisory
from gradle_deps_monitor.domain.catalog import Catalog
from gradle_deps_monitor.domain.compliance import ComplianceFinding, ComplianceSeverity
from gradle_deps_monitor.domain.finding import Finding
from gradle_deps_monitor.domain.toolchain import ToolchainFinding, ToolchainSeverity


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
