"""PolicyEvaluator — turn a :class:`Policy` + :class:`FreezeReport`
into a :class:`PolicyResult` (RFC-0018 v1).

Stateless and dependency-free: the evaluator reads only the
``has_*`` summary properties and finding collections that
:class:`FreezeReport` already exposes. No infrastructure layer
involvement.

The evaluator is intentionally tolerant: a policy with neither
``fail_on_errors`` nor any ``warn_on`` category yields an empty
:class:`PolicyResult`, which the CLI treats as a no-op.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator

from gradle_deps_monitor.domain import FreezeReport
from gradle_deps_monitor.domain.advisory import AdvisorySeverity
from gradle_deps_monitor.domain.compliance import ComplianceSeverity
from gradle_deps_monitor.domain.library_health import LibraryHealthSeverity
from gradle_deps_monitor.domain.license import LicenseTier
from gradle_deps_monitor.domain.policy import (
    Policy,
    PolicyResult,
    PolicyViolation,
    WarningCategory,
)
from gradle_deps_monitor.domain.severity import CommonSeverity
from gradle_deps_monitor.domain.toolchain import ToolchainSeverity


class PolicyEvaluator:
    """Evaluate a :class:`Policy` against a :class:`FreezeReport`."""

    def evaluate(self, report: FreezeReport, policy: Policy) -> PolicyResult:
        violations = tuple(self._iter_violations(report)) if policy.fail_on_errors else ()
        warnings = tuple(self._iter_warnings(report, policy.warn_on))
        return PolicyResult(violations=violations, warnings=warnings)

    # ------------------------------------------------------------------
    # Violations — driven by the 4 error-level ``has_*`` properties
    # ------------------------------------------------------------------

    def _iter_violations(self, report: FreezeReport) -> Iterator[PolicyViolation]:
        yield from _critical_cve_violations(report)
        yield from _compliance_error_violations(report)
        yield from _toolchain_error_violations(report)
        yield from _license_violations(report)

    # ------------------------------------------------------------------
    # Warnings — opt-in per category
    # ------------------------------------------------------------------

    def _iter_warnings(
        self,
        report: FreezeReport,
        categories: Iterable[WarningCategory],
    ) -> Iterator[PolicyViolation]:
        selected = frozenset(categories)
        if WarningCategory.HIGH_VULNERABILITY in selected:
            yield from _high_cve_warnings(report)
        if WarningCategory.COMPLIANCE in selected:
            yield from _compliance_warnings(report)
        if WarningCategory.TOOLCHAIN in selected:
            yield from _toolchain_warnings(report)
        if WarningCategory.LIBRARY_HEALTH in selected:
            yield from _library_health_warnings(report)
        if WarningCategory.DEPRECATED in selected:
            yield from _deprecated_warnings(report)
        if WarningCategory.BREAKING in selected:
            yield from _breaking_warnings(report)
        if WarningCategory.LICENSE in selected:
            yield from _license_warnings(report)


# ---------------------------------------------------------------------------
# Violation row builders (one per error-level ``has_*``)
# ---------------------------------------------------------------------------


def _critical_cve_violations(report: FreezeReport) -> Iterator[PolicyViolation]:
    for la in report.vulnerable_libraries:
        for adv in la.advisories:
            if adv.severity == AdvisorySeverity.CRITICAL:
                yield PolicyViolation(
                    category="security",
                    severity=CommonSeverity.ERROR,
                    message=f"Critical CVE {adv.ghsa_id}: {adv.summary}",
                    target=la.alias,
                )


def _compliance_error_violations(report: FreezeReport) -> Iterator[PolicyViolation]:
    for f in report.compliance_findings:
        if f.severity == ComplianceSeverity.ERROR:
            yield PolicyViolation(
                category="compliance",
                severity=CommonSeverity.ERROR,
                message=f"{f.rule_id}: {f.message}",
                target=f.alias or "catalog",
            )


def _toolchain_error_violations(report: FreezeReport) -> Iterator[PolicyViolation]:
    for f in report.toolchain_findings:
        if f.severity == ToolchainSeverity.ERROR:
            yield PolicyViolation(
                category="toolchain",
                severity=CommonSeverity.ERROR,
                message=f"{f.rule_id}: {f.message}",
                target="catalog",
            )


def _license_violations(report: FreezeReport) -> Iterator[PolicyViolation]:
    if report.license_audit is None:
        return
    for f in report.license_audit.findings:
        if f.tier == LicenseTier.STRONG_COPYLEFT:
            yield PolicyViolation(
                category="license",
                severity=CommonSeverity.ERROR,
                message=(
                    f"Strong copyleft license {f.license_name or '(not declared)'} "
                    f"on {f.coordinate}"
                ),
                target=f.alias,
            )


# ---------------------------------------------------------------------------
# Warning row builders (one per warning-level ``has_*``)
# ---------------------------------------------------------------------------


def _high_cve_warnings(report: FreezeReport) -> Iterator[PolicyViolation]:
    for la in report.vulnerable_libraries:
        for adv in la.advisories:
            if adv.severity == AdvisorySeverity.HIGH:
                yield PolicyViolation(
                    category="security",
                    severity=CommonSeverity.WARNING,
                    message=f"High CVE {adv.ghsa_id}: {adv.summary}",
                    target=la.alias,
                )


def _compliance_warnings(report: FreezeReport) -> Iterator[PolicyViolation]:
    for f in report.compliance_findings:
        if f.severity == ComplianceSeverity.WARNING:
            yield PolicyViolation(
                category="compliance",
                severity=CommonSeverity.WARNING,
                message=f"{f.rule_id}: {f.message}",
                target=f.alias or "catalog",
            )


def _toolchain_warnings(report: FreezeReport) -> Iterator[PolicyViolation]:
    for f in report.toolchain_findings:
        if f.severity == ToolchainSeverity.WARNING:
            yield PolicyViolation(
                category="toolchain",
                severity=CommonSeverity.WARNING,
                message=f"{f.rule_id}: {f.message}",
                target="catalog",
            )


def _library_health_warnings(report: FreezeReport) -> Iterator[PolicyViolation]:
    """Surface only HIGH-severity health findings; deprecation has its
    own category (the two overlap intentionally — ``deprecated``
    catches relocations/curated KB hits regardless of severity)."""
    for f in report.library_health_findings:
        if f.severity == LibraryHealthSeverity.HIGH:
            yield PolicyViolation(
                category="library-health",
                severity=CommonSeverity.WARNING,
                message=f"{f.signal.value}: {f.message}",
                target=f.alias,
            )


def _deprecated_warnings(report: FreezeReport) -> Iterator[PolicyViolation]:
    for f in report.deprecated_libraries:
        yield PolicyViolation(
            category="deprecated",
            severity=CommonSeverity.WARNING,
            message=f"{f.signal.value}: {f.message}",
            target=f.alias,
        )


def _breaking_warnings(report: FreezeReport) -> Iterator[PolicyViolation]:
    for e in report.breaking_upgrades:
        yield PolicyViolation(
            category="breaking",
            severity=CommonSeverity.WARNING,
            message=(f"Likely-breaking upgrade {e.pinned_version} → {e.latest_version}"),
            target=e.alias,
        )


def _license_warnings(report: FreezeReport) -> Iterator[PolicyViolation]:
    if report.license_audit is None:
        return
    for f in report.license_audit.findings:
        if f.tier in (LicenseTier.WEAK_COPYLEFT, LicenseTier.UNKNOWN):
            yield PolicyViolation(
                category="license",
                severity=CommonSeverity.WARNING,
                message=(
                    f"{f.tier.value.replace('_', ' ').title()} license "
                    f"{f.license_name or '(not declared)'} on {f.coordinate}"
                ),
                target=f.alias,
            )
