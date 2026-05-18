"""Tests for :class:`PolicyEvaluator` (RFC-0018 v1)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from gradle_deps_monitor.application.evaluate_policy import PolicyEvaluator
from gradle_deps_monitor.domain import FreezeReport
from gradle_deps_monitor.domain.advisory import Advisory, AdvisorySeverity, LibraryAdvisory
from gradle_deps_monitor.domain.catalog import Catalog
from gradle_deps_monitor.domain.changelog import BreakingSignal, ChangelogEntry
from gradle_deps_monitor.domain.compliance import ComplianceFinding, ComplianceSeverity
from gradle_deps_monitor.domain.library_health import (
    HealthSignal,
    LibraryHealthFinding,
    LibraryHealthSeverity,
)
from gradle_deps_monitor.domain.license import LicenseAudit, LicenseFinding, LicenseTier
from gradle_deps_monitor.domain.policy import Policy, WarningCategory
from gradle_deps_monitor.domain.severity import CommonSeverity
from gradle_deps_monitor.domain.toolchain import ToolchainFinding, ToolchainSeverity

_TS = datetime(2026, 5, 18, tzinfo=UTC)


def _empty_report(**overrides) -> FreezeReport:  # type: ignore[no-untyped-def]
    base = {
        "catalog": Catalog(
            source_path=Path("libs.versions.toml"),
            libraries=(),
            plugins=(),
            bundles=(),
        ),
        "generated_at": _TS,
    }
    base.update(overrides)
    return FreezeReport(**base)  # type: ignore[arg-type]


def _advisory(severity: AdvisorySeverity) -> Advisory:
    return Advisory(
        ghsa_id="GHSA-aaaa-bbbb-cccc",
        cve_id="CVE-2026-0001",
        severity=severity,
        summary="example",
        fixed_version="2.0.0",
        url="https://example.test/advisory",
        source="github",
    )


def _vulnerable(alias: str, severity: AdvisorySeverity) -> LibraryAdvisory:
    return LibraryAdvisory(
        alias=alias,
        coordinate="g:art",
        version="1.0.0",
        advisories=(_advisory(severity),),
    )


# ---------------------------------------------------------------------------
# Defaults — an empty policy never produces rows
# ---------------------------------------------------------------------------


class TestEmptyPolicy:
    def test_default_policy_yields_empty_result(self) -> None:
        result = PolicyEvaluator().evaluate(_empty_report(), Policy())
        assert result.violations == ()
        assert result.warnings == ()
        assert result.should_fail is False

    def test_fail_on_errors_with_clean_report_is_noop(self) -> None:
        result = PolicyEvaluator().evaluate(_empty_report(), Policy(fail_on_errors=True))
        assert result.violations == ()
        assert result.should_fail is False


# ---------------------------------------------------------------------------
# fail_on_errors — one test per error-level has_* property
# ---------------------------------------------------------------------------


class TestFailOnErrors:
    def test_critical_cve_becomes_violation(self) -> None:
        report = _empty_report(
            security_advisories=(_vulnerable("lib-a", AdvisorySeverity.CRITICAL),),
        )
        result = PolicyEvaluator().evaluate(report, Policy(fail_on_errors=True))
        assert result.should_fail is True
        assert len(result.violations) == 1
        v = result.violations[0]
        assert v.category == "security"
        assert v.severity == CommonSeverity.ERROR
        assert v.target == "lib-a"
        assert "GHSA-aaaa-bbbb-cccc" in v.message

    def test_high_cve_is_NOT_a_violation_under_fail_on_errors(self) -> None:
        """HIGH advisories are warning-level per ``has_high_vulnerabilities``."""
        report = _empty_report(
            security_advisories=(_vulnerable("lib-a", AdvisorySeverity.HIGH),),
        )
        result = PolicyEvaluator().evaluate(report, Policy(fail_on_errors=True))
        assert result.violations == ()
        assert result.should_fail is False

    def test_compliance_error_becomes_violation(self) -> None:
        report = _empty_report(
            compliance_findings=(
                ComplianceFinding(
                    rule_id="PSC-TARGET-SDK",
                    severity=ComplianceSeverity.ERROR,
                    message="targetSdk too low",
                ),
            ),
        )
        result = PolicyEvaluator().evaluate(report, Policy(fail_on_errors=True))
        assert len(result.violations) == 1
        v = result.violations[0]
        assert v.category == "compliance"
        assert v.target == "catalog"

    def test_toolchain_error_becomes_violation(self) -> None:
        report = _empty_report(
            toolchain_findings=(
                ToolchainFinding(
                    rule_id="TOOL-KC-001",
                    severity=ToolchainSeverity.ERROR,
                    message="Kotlin / KSP version mismatch",
                ),
            ),
        )
        result = PolicyEvaluator().evaluate(report, Policy(fail_on_errors=True))
        assert len(result.violations) == 1
        assert result.violations[0].category == "toolchain"

    def test_strong_copyleft_becomes_violation(self) -> None:
        report = _empty_report(
            license_audit=LicenseAudit(
                findings=(
                    LicenseFinding(
                        alias="lgpl-lib",
                        coordinate="g:art",
                        version="1.0",
                        license_name="GPL-3.0",
                        license_url=None,
                        tier=LicenseTier.STRONG_COPYLEFT,
                    ),
                ),
                libraries_audited=10,
            ),
        )
        result = PolicyEvaluator().evaluate(report, Policy(fail_on_errors=True))
        assert len(result.violations) == 1
        assert result.violations[0].category == "license"
        assert result.violations[0].target == "lgpl-lib"

    def test_no_double_counting_when_no_audit(self) -> None:
        """``license_audit=None`` must not blow up the evaluator."""
        result = PolicyEvaluator().evaluate(
            _empty_report(license_audit=None), Policy(fail_on_errors=True)
        )
        assert result.violations == ()


# ---------------------------------------------------------------------------
# warn_on — one test per warning category
# ---------------------------------------------------------------------------


class TestWarnOn:
    def test_high_cve_surfaces_when_category_selected(self) -> None:
        report = _empty_report(
            security_advisories=(_vulnerable("lib-a", AdvisorySeverity.HIGH),),
        )
        result = PolicyEvaluator().evaluate(
            report, Policy(warn_on=frozenset({WarningCategory.HIGH_VULNERABILITY}))
        )
        assert len(result.warnings) == 1
        assert result.warnings[0].category == "security"
        assert result.warnings[0].severity == CommonSeverity.WARNING
        assert result.should_fail is False

    def test_warnings_alone_do_not_fail(self) -> None:
        report = _empty_report(
            security_advisories=(_vulnerable("lib-a", AdvisorySeverity.HIGH),),
        )
        result = PolicyEvaluator().evaluate(
            report, Policy(warn_on=frozenset({WarningCategory.HIGH_VULNERABILITY}))
        )
        assert result.should_fail is False

    def test_breaking_upgrade_surfaces_when_selected(self) -> None:
        report = _empty_report(
            changelog_entries=(
                ChangelogEntry(
                    alias="kotlin-stdlib",
                    coordinate="org.jetbrains.kotlin:kotlin-stdlib",
                    pinned_version="1.9.0",
                    latest_version="2.0.0",
                    breaking_signal=BreakingSignal.LIKELY,
                    snippet=None,
                    changelog_url=None,
                ),
            ),
        )
        result = PolicyEvaluator().evaluate(
            report, Policy(warn_on=frozenset({WarningCategory.BREAKING}))
        )
        assert len(result.warnings) == 1
        assert result.warnings[0].category == "breaking"

    def test_clean_breaking_is_not_a_warning(self) -> None:
        """Only ``BreakingSignal.LIKELY`` enters the breaking category."""
        report = _empty_report(
            changelog_entries=(
                ChangelogEntry(
                    alias="kotlin-stdlib",
                    coordinate="org.jetbrains.kotlin:kotlin-stdlib",
                    pinned_version="1.9.0",
                    latest_version="2.0.0",
                    breaking_signal=BreakingSignal.CLEAN,
                    snippet=None,
                    changelog_url=None,
                ),
            ),
        )
        result = PolicyEvaluator().evaluate(
            report, Policy(warn_on=frozenset({WarningCategory.BREAKING}))
        )
        assert result.warnings == ()

    def test_deprecated_surfaces_when_selected(self) -> None:
        report = _empty_report(
            library_health_findings=(
                LibraryHealthFinding(
                    alias="old-lib",
                    coordinate="g:art",
                    version="1.0",
                    signal=HealthSignal.CURATED,
                    severity=LibraryHealthSeverity.MEDIUM,
                    message="deprecated upstream",
                    replacement=None,
                    migration_url=None,
                    days_since_release=None,
                ),
            ),
        )
        result = PolicyEvaluator().evaluate(
            report, Policy(warn_on=frozenset({WarningCategory.DEPRECATED}))
        )
        assert len(result.warnings) == 1
        assert result.warnings[0].category == "deprecated"

    def test_weak_copyleft_surfaces_when_license_selected(self) -> None:
        report = _empty_report(
            license_audit=LicenseAudit(
                findings=(
                    LicenseFinding(
                        alias="weak-lib",
                        coordinate="g:art",
                        version="1.0",
                        license_name="LGPL-3.0",
                        license_url=None,
                        tier=LicenseTier.WEAK_COPYLEFT,
                    ),
                ),
                libraries_audited=5,
            ),
        )
        result = PolicyEvaluator().evaluate(
            report, Policy(warn_on=frozenset({WarningCategory.LICENSE}))
        )
        assert len(result.warnings) == 1
        assert result.warnings[0].category == "license"

    def test_unselected_category_is_silent(self) -> None:
        """A category not in ``warn_on`` produces zero rows even when the
        underlying ``has_*`` property would be true."""
        report = _empty_report(
            security_advisories=(_vulnerable("lib-a", AdvisorySeverity.HIGH),),
        )
        result = PolicyEvaluator().evaluate(
            report, Policy(warn_on=frozenset({WarningCategory.BREAKING}))
        )
        assert result.warnings == ()


# ---------------------------------------------------------------------------
# Combined — violations + warnings in one evaluation
# ---------------------------------------------------------------------------


class TestCombined:
    def test_violations_and_warnings_coexist(self) -> None:
        report = _empty_report(
            security_advisories=(
                _vulnerable("lib-a", AdvisorySeverity.CRITICAL),
                _vulnerable("lib-b", AdvisorySeverity.HIGH),
            ),
        )
        result = PolicyEvaluator().evaluate(
            report,
            Policy(
                fail_on_errors=True,
                warn_on=frozenset({WarningCategory.HIGH_VULNERABILITY}),
            ),
        )
        assert result.should_fail is True
        assert len(result.violations) == 1
        assert result.violations[0].target == "lib-a"
        assert len(result.warnings) == 1
        assert result.warnings[0].target == "lib-b"
