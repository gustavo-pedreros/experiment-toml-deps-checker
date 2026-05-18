"""Tests for RFC-0028 console severity bucket enumeration.

Pre-fix Risk Score and Security collapsed MEDIUM/LOW into a single
``N other`` bucket when no CRITICAL/HIGH entries existed. The stress
test surfaced this as "Risk Score — 157 other" while the Markdown
report showed 137 medium + 20 low. Tests below pin the corrected
behaviour: every populated severity gets an explicit bucket.
"""

from __future__ import annotations

import io
from datetime import UTC, datetime
from pathlib import Path

from rich.console import Console

from gradle_deps_monitor.domain import Catalog, FreezeReport, Library
from gradle_deps_monitor.domain.advisory import (
    Advisory,
    AdvisorySeverity,
    LibraryAdvisory,
)
from gradle_deps_monitor.domain.risk_score import (
    LibraryRiskScore,
    RiskLevel,
    RiskScoreReport,
)
from gradle_deps_monitor.domain.version import MavenVersion
from gradle_deps_monitor.presentation.console import print_summary

_TS = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)


def _capture(report: FreezeReport) -> str:
    buf = io.StringIO()
    # force_terminal=False produces plain text without ANSI codes —
    # makes string assertions cleaner.
    con = Console(file=buf, force_terminal=False, no_color=True, width=200)
    print_summary(report, written_files=(), console=con)
    return buf.getvalue()


def _adv(severity: AdvisorySeverity) -> Advisory:
    return Advisory(
        ghsa_id="GHSA-x",
        cve_id=None,
        severity=severity,
        summary="x",
        fixed_version=None,
        url="https://example.invalid/x",
        source="github",
    )


def test_security_console_enumerates_medium_low_when_no_critical_high(tmp_path: Path) -> None:
    """When CRITICAL/HIGH are both zero, MEDIUM and LOW must appear by name."""
    catalog = Catalog(
        source_path=tmp_path / "libs.versions.toml",
        libraries=(
            Library("med", "g", "m", MavenVersion("1.0.0")),
            Library("low", "g", "l", MavenVersion("1.0.0")),
        ),
        plugins=(),
        bundles=(),
    )
    advisories = (
        LibraryAdvisory(
            alias="med",
            coordinate="g:m",
            version="1.0.0",
            advisories=(_adv(AdvisorySeverity.MEDIUM),),
        ),
        LibraryAdvisory(
            alias="low", coordinate="g:l", version="1.0.0", advisories=(_adv(AdvisorySeverity.LOW),)
        ),
    )
    report = FreezeReport(
        catalog=catalog, generated_at=_TS, security_advisories=advisories, security_scanned=True
    )
    out = _capture(report)
    # Both severity counts must appear; pre-fix output said "2 other"
    assert "1 medium" in out
    assert "1 low" in out
    assert " other" not in out  # the lazy bucket must NOT appear


def test_security_console_keeps_critical_high_when_present(tmp_path: Path) -> None:
    """CRITICAL/HIGH bucketing path stays intact; medium/low still itemised."""
    catalog = Catalog(
        source_path=tmp_path / "libs.versions.toml",
        libraries=(
            Library("crit", "g", "c", MavenVersion("1.0.0")),
            Library("med", "g", "m", MavenVersion("1.0.0")),
        ),
        plugins=(),
        bundles=(),
    )
    advisories = (
        LibraryAdvisory(
            alias="crit",
            coordinate="g:c",
            version="1.0.0",
            advisories=(_adv(AdvisorySeverity.CRITICAL),),
        ),
        LibraryAdvisory(
            alias="med",
            coordinate="g:m",
            version="1.0.0",
            advisories=(_adv(AdvisorySeverity.MEDIUM),),
        ),
    )
    report = FreezeReport(
        catalog=catalog, generated_at=_TS, security_advisories=advisories, security_scanned=True
    )
    out = _capture(report)
    assert "1 critical" in out
    assert "1 medium" in out


def test_risk_score_console_enumerates_medium_low_when_no_critical_high(tmp_path: Path) -> None:
    catalog = Catalog(
        source_path=tmp_path / "libs.versions.toml",
        libraries=(Library("a", "g", "a", MavenVersion("1.0.0")),),
        plugins=(),
        bundles=(),
    )
    scored = (
        LibraryRiskScore("m1", "g:m1", "1.0.0", 35, (), RiskLevel.MEDIUM),
        LibraryRiskScore("m2", "g:m2", "1.0.0", 30, (), RiskLevel.MEDIUM),
        LibraryRiskScore("l1", "g:l1", "1.0.0", 10, (), RiskLevel.LOW),
    )
    rsr = RiskScoreReport(scored_libraries=scored, libraries_scored=3)
    report = FreezeReport(catalog=catalog, generated_at=_TS, risk_score_report=rsr)
    out = _capture(report)
    # Pre-fix this output would have read "3 other"; post-RFC the
    # buckets are explicit.
    assert "2 medium" in out
    assert "1 low" in out
    assert " other" not in out
