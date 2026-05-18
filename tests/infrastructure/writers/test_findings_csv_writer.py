"""Tests for FindingsCsvWriter (RFC-0017 PR #2)."""

from __future__ import annotations

import csv
from datetime import UTC, datetime
from pathlib import Path

import pytest

from gradle_deps_monitor.domain import (
    Catalog,
    Finding,
    FreezeReport,
    Library,
    Severity,
)
from gradle_deps_monitor.domain.advisory import Advisory, AdvisorySeverity, LibraryAdvisory
from gradle_deps_monitor.domain.changelog import BreakingSignal, ChangelogEntry
from gradle_deps_monitor.domain.compliance import ComplianceFinding, ComplianceSeverity
from gradle_deps_monitor.domain.library_health import (
    HealthSignal,
    LibraryHealthFinding,
    LibraryHealthSeverity,
)
from gradle_deps_monitor.domain.license import (
    LicenseAudit,
    LicenseFinding,
    LicenseTier,
)
from gradle_deps_monitor.domain.toolchain import ToolchainFinding, ToolchainSeverity
from gradle_deps_monitor.domain.version import MavenVersion
from gradle_deps_monitor.infrastructure.writers.findings_csv_writer import (
    FindingsCsvWriter,
)

_TS = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)


@pytest.fixture()
def empty_report(tmp_path: Path) -> FreezeReport:
    catalog = Catalog(
        source_path=tmp_path / "libs.versions.toml",
        libraries=(),
        plugins=(),
        bundles=(),
    )
    return FreezeReport(catalog=catalog, generated_at=_TS)


@pytest.fixture()
def all_sections_report(tmp_path: Path) -> FreezeReport:
    """A report with at least one finding per section, plus a clean
    library and a non-LIKELY changelog entry that must not appear."""
    catalog = Catalog(
        source_path=tmp_path / "libs.versions.toml",
        libraries=(
            Library("retrofit", "com.squareup.retrofit2", "retrofit", MavenVersion("2.0.0")),
            Library("clean", "g", "clean", MavenVersion("1.0.0")),
        ),
        plugins=(),
        bundles=(),
    )
    health = (
        Finding(
            rule_id="catalog.inline-versions",
            severity=Severity.WARNING,
            message="literal version pinned",
        ),
    )
    compliance = (
        ComplianceFinding(
            rule_id="PSC-001",
            severity=ComplianceSeverity.ERROR,
            message="targetSdk too low",
            alias="retrofit",
            coordinate="com.squareup.retrofit2:retrofit",
        ),
    )
    toolchain = (
        ToolchainFinding(
            rule_id="TOOL-KC-001",
            severity=ToolchainSeverity.ERROR,
            message="kotlin/compose version mismatch",
            recommendation="bump compose-compiler",
        ),
    )
    lib_health = (
        LibraryHealthFinding(
            alias="retrofit",
            coordinate="com.squareup.retrofit2:retrofit",
            version="2.0.0",
            signal=HealthSignal.INACTIVE,
            severity=LibraryHealthSeverity.MEDIUM,
            message="no release in 36 months",
            replacement=None,
            migration_url=None,
        ),
    )
    security = (
        LibraryAdvisory(
            alias="retrofit",
            coordinate="com.squareup.retrofit2:retrofit",
            version="2.0.0",
            advisories=(
                Advisory(
                    ghsa_id="GHSA-xxxx-yyyy-zzzz",
                    cve_id="CVE-2024-9999",
                    severity=AdvisorySeverity.HIGH,
                    summary="malformed redirect",
                    fixed_version="2.0.1",
                    url="https://example.invalid/adv",
                    source="github",
                ),
            ),
        ),
        # Clean library — scanned, zero advisories — must NOT emit a row.
        LibraryAdvisory(alias="clean", coordinate="g:clean", version="1.0.0", advisories=()),
    )
    license_audit = LicenseAudit(
        findings=(
            LicenseFinding(
                alias="retrofit",
                coordinate="com.squareup.retrofit2:retrofit",
                version="2.0.0",
                license_name="GPL-3.0",
                license_url=None,
                tier=LicenseTier.STRONG_COPYLEFT,
            ),
        ),
        libraries_audited=2,
    )
    changelog = (
        ChangelogEntry(
            alias="retrofit",
            coordinate="com.squareup.retrofit2:retrofit",
            pinned_version="2.0.0",
            latest_version="3.0.0",
            changelog_url="https://example.invalid/release",
            breaking_signal=BreakingSignal.LIKELY,
            snippet="API: removed Call.execute()",
        ),
        # Non-LIKELY entry — must NOT emit a row.
        ChangelogEntry(
            alias="clean",
            coordinate="g:clean",
            pinned_version="1.0.0",
            latest_version="2.0.0",
            breaking_signal=BreakingSignal.CLEAN,
        ),
    )
    return FreezeReport(
        catalog=catalog,
        generated_at=_TS,
        health_findings=health,
        compliance_findings=compliance,
        toolchain_findings=toolchain,
        library_health_findings=lib_health,
        security_advisories=security,
        license_audit=license_audit,
        changelog_entries=changelog,
    )


# ---------------------------------------------------------------------------
# File creation + header
# ---------------------------------------------------------------------------


def test_creates_file_with_header(empty_report: FreezeReport, tmp_path: Path) -> None:
    dest = tmp_path / "freeze-findings.csv"
    FindingsCsvWriter().write(empty_report, dest)
    with dest.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.reader(fh))
    assert rows == [
        [
            "section",
            "rule_id",
            "severity",
            "common_severity",
            "target",
            "message",
            "recommendation",
        ]
    ]


def test_empty_report_writes_header_only(empty_report: FreezeReport, tmp_path: Path) -> None:
    dest = tmp_path / "freeze-findings.csv"
    FindingsCsvWriter().write(empty_report, dest)
    with dest.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.reader(fh))
    assert len(rows) == 1


# ---------------------------------------------------------------------------
# One row per finding across every section
# ---------------------------------------------------------------------------


def _rows_by_section(dest: Path) -> dict[str, list[dict[str, str]]]:
    by_section: dict[str, list[dict[str, str]]] = {}
    with dest.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            by_section.setdefault(row["section"], []).append(row)
    return by_section


def test_emits_one_row_per_catalog_health_finding(
    all_sections_report: FreezeReport, tmp_path: Path
) -> None:
    dest = tmp_path / "freeze-findings.csv"
    FindingsCsvWriter().write(all_sections_report, dest)
    rows = _rows_by_section(dest)["Catalog Health"]
    assert len(rows) == 1
    assert rows[0]["rule_id"] == "catalog.inline-versions"
    assert rows[0]["target"] == "catalog"


def test_emits_one_row_per_compliance_finding(
    all_sections_report: FreezeReport, tmp_path: Path
) -> None:
    dest = tmp_path / "freeze-findings.csv"
    FindingsCsvWriter().write(all_sections_report, dest)
    rows = _rows_by_section(dest)["Compliance"]
    assert len(rows) == 1
    assert rows[0]["rule_id"] == "PSC-001"
    assert rows[0]["target"] == "retrofit"


def test_emits_one_row_per_toolchain_finding(
    all_sections_report: FreezeReport, tmp_path: Path
) -> None:
    dest = tmp_path / "freeze-findings.csv"
    FindingsCsvWriter().write(all_sections_report, dest)
    rows = _rows_by_section(dest)["Toolchain"]
    assert len(rows) == 1
    assert rows[0]["recommendation"] == "bump compose-compiler"


def test_emits_synthetic_rule_id_for_library_health(
    all_sections_report: FreezeReport, tmp_path: Path
) -> None:
    """Library Health findings have no native rule_id — synthesised from signal."""
    dest = tmp_path / "freeze-findings.csv"
    FindingsCsvWriter().write(all_sections_report, dest)
    rows = _rows_by_section(dest)["Library Health"]
    assert len(rows) == 1
    assert rows[0]["rule_id"] == "library-health.inactive"
    assert rows[0]["target"] == "retrofit"


def test_emits_one_row_per_advisory_inside_library_advisory(
    all_sections_report: FreezeReport, tmp_path: Path
) -> None:
    """Security: row per Advisory, not per LibraryAdvisory. Clean libs emit nothing."""
    dest = tmp_path / "freeze-findings.csv"
    FindingsCsvWriter().write(all_sections_report, dest)
    rows = _rows_by_section(dest)["Security"]
    assert len(rows) == 1
    assert rows[0]["rule_id"] == "GHSA-xxxx-yyyy-zzzz"
    assert rows[0]["target"] == "retrofit"
    assert rows[0]["recommendation"] == "fixed in 2.0.1"


def test_license_findings_emit_synthetic_rule_id(
    all_sections_report: FreezeReport, tmp_path: Path
) -> None:
    dest = tmp_path / "freeze-findings.csv"
    FindingsCsvWriter().write(all_sections_report, dest)
    rows = _rows_by_section(dest)["License"]
    assert len(rows) == 1
    assert rows[0]["rule_id"] == "license.strong_copyleft"
    assert rows[0]["common_severity"] == "error"


def test_changelog_emits_only_likely_breaking(
    all_sections_report: FreezeReport, tmp_path: Path
) -> None:
    """CLEAN / UNKNOWN entries are informational, not findings."""
    dest = tmp_path / "freeze-findings.csv"
    FindingsCsvWriter().write(all_sections_report, dest)
    rows = _rows_by_section(dest)["Changelog"]
    assert len(rows) == 1
    assert rows[0]["rule_id"] == "changelog.breaking"
    assert rows[0]["target"] == "retrofit"


def test_total_row_count_matches_expected_sections(
    all_sections_report: FreezeReport, tmp_path: Path
) -> None:
    """1 header + 1 catalog-health + 1 compliance + 1 toolchain + 1 library-health
    + 1 security + 1 license + 1 changelog = 8 rows."""
    dest = tmp_path / "freeze-findings.csv"
    FindingsCsvWriter().write(all_sections_report, dest)
    with dest.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.reader(fh))
    assert len(rows) == 8


# ---------------------------------------------------------------------------
# Sort stability
# ---------------------------------------------------------------------------


def test_rows_sorted_by_section_then_target_then_rule_id(
    all_sections_report: FreezeReport, tmp_path: Path
) -> None:
    dest = tmp_path / "freeze-findings.csv"
    FindingsCsvWriter().write(all_sections_report, dest)
    with dest.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    keys = [(r["section"], r["target"], r["rule_id"]) for r in rows]
    assert keys == sorted(keys)


def test_no_utf8_bom(empty_report: FreezeReport, tmp_path: Path) -> None:
    dest = tmp_path / "freeze-findings.csv"
    FindingsCsvWriter().write(empty_report, dest)
    assert not dest.read_bytes().startswith(b"\xef\xbb\xbf")
