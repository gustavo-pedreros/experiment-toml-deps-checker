"""Unit tests for the compute_risk_score application service (RFC-0008)."""

from __future__ import annotations

from gradle_deps_monitor.application.compute_risk_score import (
    _parse_major,
    _score_abandonment,
    _score_blast_radius,
    _score_compliance,
    _score_cve,
    _score_license,
    _score_outdatedness,
    score_libraries,
)
from gradle_deps_monitor.domain.advisory import Advisory, AdvisorySeverity, LibraryAdvisory
from gradle_deps_monitor.domain.catalog import Library
from gradle_deps_monitor.domain.changelog import BreakingSignal, ChangelogEntry
from gradle_deps_monitor.domain.library_health import (
    HealthSignal,
    LibraryHealthFinding,
    LibraryHealthSeverity,
)
from gradle_deps_monitor.domain.license import LicenseAudit, LicenseFinding, LicenseTier
from gradle_deps_monitor.domain.module_usage import LibraryUsage, ModuleSummary, ModuleUsageMap
from gradle_deps_monitor.domain.risk_score import RiskLevel
from gradle_deps_monitor.domain.version import MavenVersion

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _lib(alias: str, group: str = "com.example") -> Library:
    return Library(alias=alias, group=group, artifact=alias, version=MavenVersion("1.0.0"))


def _advisory(severity: AdvisorySeverity = AdvisorySeverity.HIGH) -> Advisory:
    return Advisory(
        ghsa_id="GHSA-xxxx-yyyy-zzzz",
        cve_id=None,
        severity=severity,
        summary="test",
        fixed_version=None,
        url="https://example.com",
        source="github",
    )


def _la(alias: str, *severities: AdvisorySeverity) -> LibraryAdvisory:
    return LibraryAdvisory(
        alias=alias,
        coordinate=f"com.example:{alias}",
        version="1.0.0",
        advisories=tuple(_advisory(s) for s in severities),
    )


def _changelog_entry(alias: str, pinned: str, latest: str) -> ChangelogEntry:
    return ChangelogEntry(
        alias=alias,
        coordinate=f"com.example:{alias}",
        pinned_version=pinned,
        latest_version=latest,
        breaking_signal=BreakingSignal.UNKNOWN,
    )


def _health_finding(
    alias: str,
    severity: LibraryHealthSeverity,
    days: int | None = None,
) -> LibraryHealthFinding:
    return LibraryHealthFinding(
        alias=alias,
        coordinate=f"com.example:{alias}",
        version="1.0.0",
        signal=HealthSignal.INACTIVE
        if severity == LibraryHealthSeverity.MEDIUM
        else HealthSignal.CURATED,
        severity=severity,
        message="test finding",
        days_since_release=days,
    )


def _usage_map(*aliases: str, modules: int = 3) -> ModuleUsageMap:
    usages = tuple(
        LibraryUsage(
            alias=a,
            coordinate=f"com.example:{a}",
            implementation_modules=tuple(f":mod{i}" for i in range(modules)),
            api_modules=(),
            test_modules=(),
        )
        for a in aliases
    )
    return ModuleUsageMap(
        library_usages=usages,
        module_summaries=(ModuleSummary(":mod0", 1),),
        modules_scanned=1,
    )


def _license_audit_with(alias: str, tier: LicenseTier) -> LicenseAudit:
    finding = LicenseFinding(
        alias=alias,
        coordinate=f"com.example:{alias}",
        version="1.0.0",
        license_name="GPL-3.0",
        license_url=None,
        tier=tier,
    )
    return LicenseAudit(findings=(finding,), libraries_audited=1)


# ---------------------------------------------------------------------------
# _parse_major
# ---------------------------------------------------------------------------


class TestParseMajor:
    def test_simple(self) -> None:
        assert _parse_major("3.2.1") == 3

    def test_single_component(self) -> None:
        assert _parse_major("5") == 5

    def test_non_numeric_returns_zero(self) -> None:
        assert _parse_major("alpha") == 0

    def test_empty_returns_zero(self) -> None:
        assert _parse_major("") == 0


# ---------------------------------------------------------------------------
# _score_outdatedness
# ---------------------------------------------------------------------------


class TestScoreOutdatedness:
    def test_no_entry_zero(self) -> None:
        d = _score_outdatedness("unknown", {}, 25)
        assert d.score == 0
        assert "up to date" in d.detail

    def test_same_major_zero(self) -> None:
        entry = _changelog_entry("lib", "3.1.0", "3.5.0")
        d = _score_outdatedness("lib", {"lib": entry}, 25)
        assert d.score == 0

    def test_one_major_behind(self) -> None:
        entry = _changelog_entry("lib", "2.0.0", "3.0.0")
        d = _score_outdatedness("lib", {"lib": entry}, 25)
        assert d.score == 20

    def test_two_majors_behind_full_cap(self) -> None:
        entry = _changelog_entry("lib", "1.0.0", "3.0.0")
        d = _score_outdatedness("lib", {"lib": entry}, 25)
        assert d.score == 25

    def test_score_capped_at_cap(self) -> None:
        entry = _changelog_entry("lib", "1.0.0", "4.0.0")
        d = _score_outdatedness("lib", {"lib": entry}, 20)
        assert d.score <= 20


# ---------------------------------------------------------------------------
# _score_cve
# ---------------------------------------------------------------------------


class TestScoreCve:
    def test_no_advisory_zero(self) -> None:
        d = _score_cve("lib", {}, 30)
        assert d.score == 0

    def test_single_critical(self) -> None:
        la = _la("lib", AdvisorySeverity.CRITICAL)
        d = _score_cve("lib", {"lib": la}, 30)
        assert d.score == 30

    def test_single_high(self) -> None:
        la = _la("lib", AdvisorySeverity.HIGH)
        d = _score_cve("lib", {"lib": la}, 30)
        assert d.score == 20

    def test_two_medium_capped(self) -> None:
        la = _la("lib", AdvisorySeverity.MEDIUM, AdvisorySeverity.MEDIUM)
        d = _score_cve("lib", {"lib": la}, 30)
        assert d.score == 20  # 10+10=20, capped at 30 → 20

    def test_multiple_advisories_capped_at_cap(self) -> None:
        la = _la("lib", AdvisorySeverity.HIGH, AdvisorySeverity.HIGH, AdvisorySeverity.HIGH)
        d = _score_cve("lib", {"lib": la}, 30)
        assert d.score == 30  # 20+20+20=60, capped at 30


# ---------------------------------------------------------------------------
# _score_abandonment
# ---------------------------------------------------------------------------


class TestScoreAbandonment:
    def test_no_finding_zero(self) -> None:
        d = _score_abandonment("lib", {}, 15)
        assert d.score == 0

    def test_high_severity_full_cap(self) -> None:
        f = _health_finding("lib", LibraryHealthSeverity.HIGH)
        d = _score_abandonment("lib", {"lib": f}, 15)
        assert d.score == 15

    def test_medium_2_years(self) -> None:
        f = _health_finding("lib", LibraryHealthSeverity.MEDIUM, days=730)
        d = _score_abandonment("lib", {"lib": f}, 15)
        assert d.score == 7

    def test_medium_3_years(self) -> None:
        f = _health_finding("lib", LibraryHealthSeverity.MEDIUM, days=1095)
        d = _score_abandonment("lib", {"lib": f}, 15)
        assert d.score == 11

    def test_medium_4_years_full_cap(self) -> None:
        f = _health_finding("lib", LibraryHealthSeverity.MEDIUM, days=1460)
        d = _score_abandonment("lib", {"lib": f}, 15)
        assert d.score == 15


# ---------------------------------------------------------------------------
# _score_blast_radius
# ---------------------------------------------------------------------------


class TestScoreBlastRadius:
    def test_no_map_zero(self) -> None:
        d = _score_blast_radius("lib", None, 15)
        assert d.score == 0
        assert "not scanned" in d.detail

    def test_not_in_map_zero(self) -> None:
        um = _usage_map("other")
        d = _score_blast_radius("lib", um, 15)
        assert d.score == 0

    def test_1_to_5_modules(self) -> None:
        um = _usage_map("lib", modules=3)
        d = _score_blast_radius("lib", um, 15)
        assert d.score == 3

    def test_6_to_15_modules(self) -> None:
        um = _usage_map("lib", modules=10)
        d = _score_blast_radius("lib", um, 15)
        assert d.score == 7

    def test_16_to_30_modules(self) -> None:
        um = _usage_map("lib", modules=20)
        d = _score_blast_radius("lib", um, 15)
        assert d.score == 11

    def test_31_plus_modules_full_cap(self) -> None:
        um = _usage_map("lib", modules=50)
        d = _score_blast_radius("lib", um, 15)
        assert d.score == 15


# ---------------------------------------------------------------------------
# _score_compliance
# ---------------------------------------------------------------------------


class TestScoreCompliance:
    def test_always_zero(self) -> None:
        d = _score_compliance(10)
        assert d.score == 0
        assert "catalog-level" in d.detail


# ---------------------------------------------------------------------------
# _score_license
# ---------------------------------------------------------------------------


class TestScoreLicense:
    def test_no_audit_zero(self) -> None:
        d = _score_license("lib", {}, None, 5)
        assert d.score == 0

    def test_permissive_zero(self) -> None:
        audit = LicenseAudit(findings=(), libraries_audited=5)
        d = _score_license("lib", {}, audit, 5)
        assert d.score == 0

    def test_strong_copyleft_full_cap(self) -> None:
        audit = _license_audit_with("lib", LicenseTier.STRONG_COPYLEFT)
        finding = {f.alias: f for f in audit.findings}
        d = _score_license("lib", finding, audit, 5)
        assert d.score == 5

    def test_weak_copyleft_half_cap(self) -> None:
        audit = _license_audit_with("lib", LicenseTier.WEAK_COPYLEFT)
        finding = {f.alias: f for f in audit.findings}
        d = _score_license("lib", finding, audit, 5)
        assert 1 <= d.score < 5

    def test_unknown_license(self) -> None:
        audit = _license_audit_with("lib", LicenseTier.UNKNOWN)
        finding = {f.alias: f for f in audit.findings}
        d = _score_license("lib", finding, audit, 5)
        assert d.score >= 1


# ---------------------------------------------------------------------------
# score_libraries — integration
# ---------------------------------------------------------------------------


class TestScoreLibraries:
    def test_empty_catalog(self) -> None:
        rsr = score_libraries((), (), (), (), None, None)
        assert rsr.libraries_scored == 0
        assert rsr.scored_libraries == ()

    def test_zero_signal_library_not_included(self) -> None:
        lib = _lib("clean")
        rsr = score_libraries((lib,), (), (), (), None, None)
        assert rsr.libraries_scored == 1
        assert rsr.scored_libraries == ()  # score=0, not included

    def test_cve_library_included(self) -> None:
        lib = _lib("vuln")
        la = _la("vuln", AdvisorySeverity.HIGH)
        rsr = score_libraries((lib,), (), (la,), (), None, None)
        assert len(rsr.scored_libraries) == 1
        assert rsr.scored_libraries[0].alias == "vuln"
        assert rsr.scored_libraries[0].total_score == 20

    def test_sorted_descending(self) -> None:
        libs = (_lib("a"), _lib("b"), _lib("c"))
        advisories = (
            _la("a", AdvisorySeverity.LOW),  # 5 pts
            _la("b", AdvisorySeverity.CRITICAL),  # 30 pts
            _la("c", AdvisorySeverity.MEDIUM),  # 10 pts
        )
        rsr = score_libraries(libs, (), advisories, (), None, None)
        scores = [lib.total_score for lib in rsr.scored_libraries]
        assert scores == sorted(scores, reverse=True)
        assert rsr.scored_libraries[0].alias == "b"

    def test_multiple_dimensions_sum(self) -> None:
        lib = _lib("multi")
        la = _la("multi", AdvisorySeverity.HIGH)  # +20 CVE
        entry = _changelog_entry("multi", "1.0.0", "3.0.0")  # +25 outdatedness (2 majors)
        rsr = score_libraries((lib,), (entry,), (la,), (), None, None)
        assert rsr.scored_libraries[0].total_score == 45

    def test_risk_level_assigned(self) -> None:
        lib = _lib("critical-lib")
        la = _la("critical-lib", AdvisorySeverity.CRITICAL)  # 30 pts
        entry = _changelog_entry("critical-lib", "1.0.0", "4.0.0")  # 25 pts (≥2 majors)
        health = _health_finding("critical-lib", LibraryHealthSeverity.HIGH)  # 15 pts
        rsr = score_libraries((lib,), (entry,), (la,), (health,), None, None)
        scored = rsr.scored_libraries[0]
        # 30+25+15 = 70 → CRITICAL
        assert scored.total_score == 70
        assert scored.level == RiskLevel.CRITICAL
