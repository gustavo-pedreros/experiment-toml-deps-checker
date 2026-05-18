"""Tests for InventoryCsvWriter (RFC-0017 PR #1 tracer)."""

from __future__ import annotations

import csv
from datetime import UTC, datetime
from pathlib import Path

import pytest

from gradle_deps_monitor.domain import Bundle, Catalog, FreezeReport, Library, Plugin
from gradle_deps_monitor.domain.version import MavenVersion
from gradle_deps_monitor.infrastructure.writers.inventory_csv_writer import (
    InventoryCsvWriter,
)

_TS = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)


@pytest.fixture()
def report(tmp_path: Path) -> FreezeReport:
    catalog = Catalog(
        source_path=tmp_path / "gradle" / "libs.versions.toml",
        libraries=(
            Library(
                "kotlin-stdlib", "org.jetbrains.kotlin", "kotlin-stdlib", MavenVersion("2.0.0")
            ),
            Library("compose-ui", "androidx.compose.ui", "ui", MavenVersion("1.6.4")),
            Library("agp-api", "com.android.tools.build", "gradle-api", MavenVersion("8.3.0-rc02")),
        ),
        plugins=(Plugin("agp", "com.android.application", MavenVersion("8.3.0-rc02")),),
        bundles=(Bundle("compose", ("compose-ui",)),),
    )
    return FreezeReport(catalog=catalog, generated_at=_TS)


@pytest.fixture()
def empty_report(tmp_path: Path) -> FreezeReport:
    catalog = Catalog(
        source_path=tmp_path / "libs.versions.toml",
        libraries=(),
        plugins=(),
        bundles=(),
    )
    return FreezeReport(catalog=catalog, generated_at=_TS)


# ---------------------------------------------------------------------------
# File creation + header
# ---------------------------------------------------------------------------


def test_creates_file(report: FreezeReport, tmp_path: Path) -> None:
    dest = tmp_path / "freeze-inventory.csv"
    InventoryCsvWriter().write(report, dest)
    assert dest.exists()


def test_creates_parent_dirs(report: FreezeReport, tmp_path: Path) -> None:
    dest = tmp_path / "nested" / "output" / "freeze-inventory.csv"
    InventoryCsvWriter().write(report, dest)
    assert dest.exists()


def test_header_row_matches_column_contract(report: FreezeReport, tmp_path: Path) -> None:
    """Column order is part of the file's contract (RFC-0017 §1)."""
    dest = tmp_path / "freeze-inventory.csv"
    InventoryCsvWriter().write(report, dest)
    with dest.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.reader(fh))
    assert rows[0] == [
        "alias",
        "coordinate",
        "version",
        "stability_tier",
        "latest_stable",
        "drift",
        "risk_score",
        "risk_level",
        "usage_count",
        "vulnerability_count",
        "compliance_issues",
        "license_tier",
        "health_status",
        "bom_parent",
        "duplicate_of",
    ]


# ---------------------------------------------------------------------------
# Row content + ordering
# ---------------------------------------------------------------------------


def test_one_row_per_library(report: FreezeReport, tmp_path: Path) -> None:
    dest = tmp_path / "freeze-inventory.csv"
    InventoryCsvWriter().write(report, dest)
    with dest.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.reader(fh))
    # 1 header + 3 libraries
    assert len(rows) == 4


def test_rows_sorted_by_alias(report: FreezeReport, tmp_path: Path) -> None:
    dest = tmp_path / "freeze-inventory.csv"
    InventoryCsvWriter().write(report, dest)
    with dest.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.reader(fh))
    aliases = [row[0] for row in rows[1:]]
    assert aliases == sorted(aliases)
    assert aliases == ["agp-api", "compose-ui", "kotlin-stdlib"]


def test_coordinate_column_joins_group_artifact(report: FreezeReport, tmp_path: Path) -> None:
    dest = tmp_path / "freeze-inventory.csv"
    InventoryCsvWriter().write(report, dest)
    with dest.open(encoding="utf-8", newline="") as fh:
        rows = {row[0]: row for row in csv.reader(fh) if row[0] != "alias"}
    assert rows["kotlin-stdlib"][1] == "org.jetbrains.kotlin:kotlin-stdlib"
    assert rows["compose-ui"][1] == "androidx.compose.ui:ui"


def test_version_column_renders_raw(report: FreezeReport, tmp_path: Path) -> None:
    """Pre-release suffix preserved verbatim."""
    dest = tmp_path / "freeze-inventory.csv"
    InventoryCsvWriter().write(report, dest)
    with dest.open(encoding="utf-8", newline="") as fh:
        rows = {row[0]: row for row in csv.reader(fh) if row[0] != "alias"}
    assert rows["agp-api"][2] == "8.3.0-rc02"


# ---------------------------------------------------------------------------
# Empty catalog
# ---------------------------------------------------------------------------


def test_empty_catalog_writes_header_only(empty_report: FreezeReport, tmp_path: Path) -> None:
    dest = tmp_path / "freeze-inventory.csv"
    InventoryCsvWriter().write(empty_report, dest)
    with dest.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.reader(fh))
    assert len(rows) == 1  # header only
    assert rows[0][0:3] == ["alias", "coordinate", "version"]


# ---------------------------------------------------------------------------
# CSV escaping safety
# ---------------------------------------------------------------------------


def test_handles_commas_in_field_values(tmp_path: Path) -> None:
    """A coordinate string containing commas would break a naive write."""
    catalog = Catalog(
        source_path=tmp_path / "libs.versions.toml",
        libraries=(Library("weird", "com.example,with-comma", "art,name", MavenVersion("1.0.0")),),
        plugins=(),
        bundles=(),
    )
    report = FreezeReport(catalog=catalog, generated_at=_TS)
    dest = tmp_path / "freeze-inventory.csv"
    InventoryCsvWriter().write(report, dest)
    with dest.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.reader(fh))
    # csv module quotes the field; reader unquotes — round-trip clean
    assert rows[1][0] == "weird"
    assert rows[1][1] == "com.example,with-comma:art,name"
    assert rows[1][2] == "1.0.0"


def test_handles_double_quotes_in_field_values(tmp_path: Path) -> None:
    catalog = Catalog(
        source_path=tmp_path / "libs.versions.toml",
        libraries=(Library('quote"ish', "com.example", "art", MavenVersion("1.0.0")),),
        plugins=(),
        bundles=(),
    )
    report = FreezeReport(catalog=catalog, generated_at=_TS)
    dest = tmp_path / "freeze-inventory.csv"
    InventoryCsvWriter().write(report, dest)
    with dest.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.reader(fh))
    assert rows[1][0] == 'quote"ish'


# ---------------------------------------------------------------------------
# RFC-0017 PR #2 — enrichment columns
# ---------------------------------------------------------------------------


def _row_by_alias(dest: Path, alias: str) -> dict[str, str]:
    """Read a single library row by alias as {column: value}."""
    with dest.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            if row["alias"] == alias:
                return row
    raise AssertionError(f"alias {alias!r} not found in {dest}")


def test_stability_tier_surfaces_pre_1_0(tmp_path: Path) -> None:
    """RFC-0026: naked 0.x.y classify as pre_1_0, not stable."""
    catalog = Catalog(
        source_path=tmp_path / "libs.versions.toml",
        libraries=(Library("young", "g", "art", MavenVersion("0.5.0")),),
        plugins=(),
        bundles=(),
    )
    report = FreezeReport(catalog=catalog, generated_at=_TS)
    dest = tmp_path / "freeze-inventory.csv"
    InventoryCsvWriter().write(report, dest)
    assert _row_by_alias(dest, "young")["stability_tier"] == "pre_1_0"


def test_latest_stable_and_drift_populated_from_status(tmp_path: Path) -> None:
    from gradle_deps_monitor.domain.version_status import LibraryVersionStatus, VersionDrift

    catalog = Catalog(
        source_path=tmp_path / "libs.versions.toml",
        libraries=(Library("lib", "g", "art", MavenVersion("1.0.0")),),
        plugins=(),
        bundles=(),
    )
    status = LibraryVersionStatus(
        alias="lib",
        coordinate="g:art",
        pinned=MavenVersion("1.0.0"),
        latest=MavenVersion("2.0.0"),
        drift=VersionDrift.MAJOR,
    )
    report = FreezeReport(catalog=catalog, generated_at=_TS, library_version_statuses=(status,))
    dest = tmp_path / "freeze-inventory.csv"
    InventoryCsvWriter().write(report, dest)
    row = _row_by_alias(dest, "lib")
    assert row["latest_stable"] == "2.0.0"
    assert row["drift"] == "major"


def test_latest_stable_and_drift_empty_when_resolver_absent(tmp_path: Path) -> None:
    catalog = Catalog(
        source_path=tmp_path / "libs.versions.toml",
        libraries=(Library("lib", "g", "art", MavenVersion("1.0.0")),),
        plugins=(),
        bundles=(),
    )
    report = FreezeReport(catalog=catalog, generated_at=_TS)
    dest = tmp_path / "freeze-inventory.csv"
    InventoryCsvWriter().write(report, dest)
    row = _row_by_alias(dest, "lib")
    assert row["latest_stable"] == ""
    assert row["drift"] == ""


def test_risk_score_empty_when_disabled(tmp_path: Path) -> None:
    catalog = Catalog(
        source_path=tmp_path / "libs.versions.toml",
        libraries=(Library("lib", "g", "art", MavenVersion("1.0.0")),),
        plugins=(),
        bundles=(),
    )
    report = FreezeReport(catalog=catalog, generated_at=_TS)
    dest = tmp_path / "freeze-inventory.csv"
    InventoryCsvWriter().write(report, dest)
    row = _row_by_alias(dest, "lib")
    assert row["risk_score"] == ""
    assert row["risk_level"] == ""


def test_risk_score_populated_when_enabled(tmp_path: Path) -> None:
    from gradle_deps_monitor.domain.risk_score import (
        LibraryRiskScore,
        RiskLevel,
        RiskScoreReport,
    )

    catalog = Catalog(
        source_path=tmp_path / "libs.versions.toml",
        libraries=(
            Library("hot", "g", "hot", MavenVersion("1.0.0")),
            Library("cold", "g", "cold", MavenVersion("1.0.0")),
        ),
        plugins=(),
        bundles=(),
    )
    rsr = RiskScoreReport(
        scored_libraries=(
            LibraryRiskScore(
                alias="hot",
                coordinate="g:hot",
                version="1.0.0",
                total_score=72,
                breakdown=(),
                level=RiskLevel.HIGH,
            ),
        ),
        libraries_scored=2,
    )
    report = FreezeReport(catalog=catalog, generated_at=_TS, risk_score_report=rsr)
    dest = tmp_path / "freeze-inventory.csv"
    InventoryCsvWriter().write(report, dest)
    hot = _row_by_alias(dest, "hot")
    cold = _row_by_alias(dest, "cold")
    assert hot["risk_score"] == "72"
    assert hot["risk_level"] == "high"
    # libs not in scored_libraries had total_score 0 and effective level NONE
    assert cold["risk_score"] == "0"
    assert cold["risk_level"] == "none"


def test_usage_count_populated_when_module_usage_enabled(tmp_path: Path) -> None:
    from gradle_deps_monitor.domain.module_usage import LibraryUsage, ModuleUsageMap

    catalog = Catalog(
        source_path=tmp_path / "libs.versions.toml",
        libraries=(Library("lib", "g", "art", MavenVersion("1.0.0")),),
        plugins=(),
        bundles=(),
    )
    usage_map = ModuleUsageMap(
        library_usages=(
            LibraryUsage(
                alias="lib",
                coordinate="g:art",
                implementation_modules=(":a", ":b"),
                api_modules=(":c",),
                test_modules=(),
            ),
        ),
        module_summaries=(),
        modules_scanned=3,
        findings=(),
    )
    report = FreezeReport(catalog=catalog, generated_at=_TS, module_usage_map=usage_map)
    dest = tmp_path / "freeze-inventory.csv"
    InventoryCsvWriter().write(report, dest)
    # direct_count = implementation + api = 2 + 1 = 3
    assert _row_by_alias(dest, "lib")["usage_count"] == "3"


def test_usage_count_empty_when_flag_off(tmp_path: Path) -> None:
    catalog = Catalog(
        source_path=tmp_path / "libs.versions.toml",
        libraries=(Library("lib", "g", "art", MavenVersion("1.0.0")),),
        plugins=(),
        bundles=(),
    )
    report = FreezeReport(catalog=catalog, generated_at=_TS)  # module_usage_map=None
    dest = tmp_path / "freeze-inventory.csv"
    InventoryCsvWriter().write(report, dest)
    assert _row_by_alias(dest, "lib")["usage_count"] == ""


def test_vulnerability_count_populated_when_scanned(tmp_path: Path) -> None:
    from gradle_deps_monitor.domain.advisory import (
        Advisory,
        AdvisorySeverity,
        LibraryAdvisory,
    )

    catalog = Catalog(
        source_path=tmp_path / "libs.versions.toml",
        libraries=(
            Library("vuln", "g", "v", MavenVersion("1.0.0")),
            Library("clean", "g", "c", MavenVersion("1.0.0")),
        ),
        plugins=(),
        bundles=(),
    )
    vuln_adv = LibraryAdvisory(
        alias="vuln",
        coordinate="g:v",
        version="1.0.0",
        advisories=(
            Advisory(
                ghsa_id="GHSA-aaaa-bbbb-cccc",
                cve_id="CVE-2024-0001",
                severity=AdvisorySeverity.HIGH,
                summary="boom",
                fixed_version="1.0.1",
                url="https://example.invalid/adv",
                source="github",
            ),
        ),
    )
    clean_adv = LibraryAdvisory(
        alias="clean",
        coordinate="g:c",
        version="1.0.0",
        advisories=(),
    )
    report = FreezeReport(
        catalog=catalog, generated_at=_TS, security_advisories=(vuln_adv, clean_adv)
    )
    dest = tmp_path / "freeze-inventory.csv"
    InventoryCsvWriter().write(report, dest)
    assert _row_by_alias(dest, "vuln")["vulnerability_count"] == "1"
    # Scanner ran, clean lib explicitly has zero — distinct from "didn't scan"
    assert _row_by_alias(dest, "clean")["vulnerability_count"] == "0"


def test_vulnerability_count_empty_when_scanner_absent(tmp_path: Path) -> None:
    catalog = Catalog(
        source_path=tmp_path / "libs.versions.toml",
        libraries=(Library("lib", "g", "art", MavenVersion("1.0.0")),),
        plugins=(),
        bundles=(),
    )
    report = FreezeReport(catalog=catalog, generated_at=_TS)  # security_advisories=()
    dest = tmp_path / "freeze-inventory.csv"
    InventoryCsvWriter().write(report, dest)
    assert _row_by_alias(dest, "lib")["vulnerability_count"] == ""


def test_compliance_issues_joins_multiple_rule_ids(tmp_path: Path) -> None:
    from gradle_deps_monitor.domain.compliance import ComplianceFinding, ComplianceSeverity

    catalog = Catalog(
        source_path=tmp_path / "libs.versions.toml",
        libraries=(Library("lib", "g", "art", MavenVersion("1.0.0")),),
        plugins=(),
        bundles=(),
    )
    cf1 = ComplianceFinding(
        rule_id="PSC-001",
        severity=ComplianceSeverity.ERROR,
        message="x",
        alias="lib",
        coordinate="g:art",
    )
    cf2 = ComplianceFinding(
        rule_id="PSC-002",
        severity=ComplianceSeverity.WARNING,
        message="y",
        alias="lib",
        coordinate="g:art",
    )
    report = FreezeReport(catalog=catalog, generated_at=_TS, compliance_findings=(cf1, cf2))
    dest = tmp_path / "freeze-inventory.csv"
    InventoryCsvWriter().write(report, dest)
    assert _row_by_alias(dest, "lib")["compliance_issues"] == "PSC-001,PSC-002"


def test_license_tier_permissive_by_absence_when_audit_ran(tmp_path: Path) -> None:
    from gradle_deps_monitor.domain.license import LicenseAudit

    catalog = Catalog(
        source_path=tmp_path / "libs.versions.toml",
        libraries=(Library("perm", "g", "art", MavenVersion("1.0.0")),),
        plugins=(),
        bundles=(),
    )
    audit = LicenseAudit(findings=(), libraries_audited=1)
    report = FreezeReport(catalog=catalog, generated_at=_TS, license_audit=audit)
    dest = tmp_path / "freeze-inventory.csv"
    InventoryCsvWriter().write(report, dest)
    assert _row_by_alias(dest, "perm")["license_tier"] == "permissive"


def test_license_tier_reflects_finding_for_flagged_library(tmp_path: Path) -> None:
    from gradle_deps_monitor.domain.license import LicenseAudit, LicenseFinding, LicenseTier

    catalog = Catalog(
        source_path=tmp_path / "libs.versions.toml",
        libraries=(Library("copyleft", "g", "art", MavenVersion("1.0.0")),),
        plugins=(),
        bundles=(),
    )
    finding = LicenseFinding(
        alias="copyleft",
        coordinate="g:art",
        version="1.0.0",
        license_name="GPL-3.0",
        license_url=None,
        tier=LicenseTier.STRONG_COPYLEFT,
    )
    audit = LicenseAudit(findings=(finding,), libraries_audited=1)
    report = FreezeReport(catalog=catalog, generated_at=_TS, license_audit=audit)
    dest = tmp_path / "freeze-inventory.csv"
    InventoryCsvWriter().write(report, dest)
    assert _row_by_alias(dest, "copyleft")["license_tier"] == "strong_copyleft"


def test_health_status_active_when_scanner_ran_no_finding(tmp_path: Path) -> None:
    from gradle_deps_monitor.domain.library_health import (
        HealthSignal,
        LibraryHealthFinding,
        LibraryHealthSeverity,
    )

    catalog = Catalog(
        source_path=tmp_path / "libs.versions.toml",
        libraries=(
            Library("ok", "g", "ok", MavenVersion("1.0.0")),
            Library("dead", "g", "dead", MavenVersion("1.0.0")),
        ),
        plugins=(),
        bundles=(),
    )
    dead_finding = LibraryHealthFinding(
        alias="dead",
        coordinate="g:dead",
        version="1.0.0",
        signal=HealthSignal.INACTIVE,
        severity=LibraryHealthSeverity.HIGH,
        message="abandoned",
    )
    report = FreezeReport(
        catalog=catalog, generated_at=_TS, library_health_findings=(dead_finding,)
    )
    dest = tmp_path / "freeze-inventory.csv"
    InventoryCsvWriter().write(report, dest)
    assert _row_by_alias(dest, "ok")["health_status"] == "active"
    assert _row_by_alias(dest, "dead")["health_status"] == "inactive"


def test_bom_parent_from_library_bom_alias(tmp_path: Path) -> None:
    catalog = Catalog(
        source_path=tmp_path / "libs.versions.toml",
        libraries=(
            Library(
                "compose-ui",
                "androidx.compose.ui",
                "ui",
                MavenVersion("1.6.4"),
                bom_alias="compose_bom",
            ),
            Library("standalone", "g", "art", MavenVersion("1.0.0")),
        ),
        plugins=(),
        bundles=(),
    )
    report = FreezeReport(catalog=catalog, generated_at=_TS)
    dest = tmp_path / "freeze-inventory.csv"
    InventoryCsvWriter().write(report, dest)
    assert _row_by_alias(dest, "compose-ui")["bom_parent"] == "compose_bom"
    assert _row_by_alias(dest, "standalone")["bom_parent"] == ""


def test_duplicate_of_cross_section_join(tmp_path: Path) -> None:
    """Issue #13: same group:artifact under multiple aliases links them.

    Pre-fix the reader had to manually correlate Catalog Health's
    duplicate-library finding with Security's per-library CVE row;
    post-RFC the inventory row for ``core_okhttp`` carries
    ``duplicate_of=legacy_okhttp`` and vice-versa, making the
    compound story visible at-a-glance.
    """
    catalog = Catalog(
        source_path=tmp_path / "libs.versions.toml",
        libraries=(
            Library("core_okhttp", "com.squareup.okhttp3", "okhttp", MavenVersion("5.3.2")),
            Library("legacy_okhttp", "com.squareup.okhttp3", "okhttp", MavenVersion("4.2.2")),
            Library("solo", "g", "solo", MavenVersion("1.0.0")),
        ),
        plugins=(),
        bundles=(),
    )
    report = FreezeReport(catalog=catalog, generated_at=_TS)
    dest = tmp_path / "freeze-inventory.csv"
    InventoryCsvWriter().write(report, dest)
    assert _row_by_alias(dest, "core_okhttp")["duplicate_of"] == "legacy_okhttp"
    assert _row_by_alias(dest, "legacy_okhttp")["duplicate_of"] == "core_okhttp"
    assert _row_by_alias(dest, "solo")["duplicate_of"] == ""


def test_no_utf8_bom(tmp_path: Path) -> None:
    """RFC-0017 explicitly rejects the BOM — Python consumers see it as data."""
    catalog = Catalog(
        source_path=tmp_path / "libs.versions.toml",
        libraries=(Library("a", "g", "art", MavenVersion("1.0.0")),),
        plugins=(),
        bundles=(),
    )
    report = FreezeReport(catalog=catalog, generated_at=_TS)
    dest = tmp_path / "freeze-inventory.csv"
    InventoryCsvWriter().write(report, dest)
    raw = dest.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
