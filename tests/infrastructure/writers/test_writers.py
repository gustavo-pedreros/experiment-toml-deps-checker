"""Tests for MarkdownWriter and JsonWriter."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from gradle_deps_monitor.domain import (
    Bundle,
    Catalog,
    Finding,
    FreezeReport,
    Library,
    Plugin,
    Severity,
)
from gradle_deps_monitor.domain.rich_version import RichVersion
from gradle_deps_monitor.domain.version import MavenVersion
from gradle_deps_monitor.infrastructure.writers.json_writer import JsonWriter
from gradle_deps_monitor.infrastructure.writers.markdown_writer import MarkdownWriter

# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------

_TS = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)


@pytest.fixture()
def full_report(tmp_path: Path) -> FreezeReport:
    catalog = Catalog(
        source_path=tmp_path / "gradle" / "libs.versions.toml",
        libraries=(
            Library(
                "kotlin-stdlib", "org.jetbrains.kotlin", "kotlin-stdlib", MavenVersion("2.0.0")
            ),
            Library("compose-ui", "androidx.compose.ui", "ui", MavenVersion("1.6.4")),
            Library("agp-api", "com.android.tools.build", "gradle-api", MavenVersion("8.3.0-rc02")),
        ),
        plugins=(
            Plugin("agp", "com.android.application", MavenVersion("8.3.0-rc02")),
            Plugin("kotlin-android", "org.jetbrains.kotlin.android", MavenVersion("2.0.0")),
        ),
        bundles=(Bundle("compose", ("compose-ui", "compose-runtime")),),
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
# MarkdownWriter — file creation
# ---------------------------------------------------------------------------


def test_markdown_creates_file(full_report: FreezeReport, tmp_path: Path) -> None:
    dest = tmp_path / "reports" / "freeze.md"
    MarkdownWriter().write(full_report, dest)
    assert dest.exists()


def test_markdown_creates_parent_dirs(full_report: FreezeReport, tmp_path: Path) -> None:
    dest = tmp_path / "a" / "b" / "c" / "freeze.md"
    MarkdownWriter().write(full_report, dest)
    assert dest.exists()


def test_markdown_contains_header(full_report: FreezeReport, tmp_path: Path) -> None:
    dest = tmp_path / "freeze.md"
    MarkdownWriter().write(full_report, dest)
    content = dest.read_text(encoding="utf-8")
    assert "# Gradle Dependency Freeze Report" in content


def test_markdown_contains_generated_at(full_report: FreezeReport, tmp_path: Path) -> None:
    dest = tmp_path / "freeze.md"
    MarkdownWriter().write(full_report, dest)
    assert "2024-06-01T12:00:00+00:00" in dest.read_text(encoding="utf-8")


def test_markdown_contains_all_library_aliases(full_report: FreezeReport, tmp_path: Path) -> None:
    dest = tmp_path / "freeze.md"
    MarkdownWriter().write(full_report, dest)
    content = dest.read_text(encoding="utf-8")
    for lib in full_report.catalog.libraries:
        assert lib.alias in content


def test_markdown_libraries_sorted_by_alias(full_report: FreezeReport, tmp_path: Path) -> None:
    dest = tmp_path / "freeze.md"
    MarkdownWriter().write(full_report, dest)
    content = dest.read_text(encoding="utf-8")
    # Verify aliases appear in alphabetical order by checking ascending positions
    sorted_aliases = sorted(lib.alias for lib in full_report.catalog.libraries)
    positions = [content.index(a) for a in sorted_aliases]
    assert positions == sorted(positions)


def test_markdown_contains_stability(full_report: FreezeReport, tmp_path: Path) -> None:
    dest = tmp_path / "freeze.md"
    MarkdownWriter().write(full_report, dest)
    content = dest.read_text(encoding="utf-8")
    assert "stable" in content
    assert "rc" in content


def test_markdown_contains_plugin_section(full_report: FreezeReport, tmp_path: Path) -> None:
    dest = tmp_path / "freeze.md"
    MarkdownWriter().write(full_report, dest)
    content = dest.read_text(encoding="utf-8")
    assert "## Plugins" in content
    assert "agp" in content


def test_markdown_contains_bundle_section(full_report: FreezeReport, tmp_path: Path) -> None:
    dest = tmp_path / "freeze.md"
    MarkdownWriter().write(full_report, dest)
    assert "## Bundles" in dest.read_text(encoding="utf-8")


def test_markdown_omits_empty_sections(empty_report: FreezeReport, tmp_path: Path) -> None:
    dest = tmp_path / "freeze.md"
    MarkdownWriter().write(empty_report, dest)
    content = dest.read_text(encoding="utf-8")
    assert "## Libraries" not in content
    assert "## Plugins" not in content
    assert "## Bundles" not in content


def test_markdown_ends_with_newline(full_report: FreezeReport, tmp_path: Path) -> None:
    dest = tmp_path / "freeze.md"
    MarkdownWriter().write(full_report, dest)
    assert dest.read_text(encoding="utf-8").endswith("\n")


# ---------------------------------------------------------------------------
# JsonWriter — structure
# ---------------------------------------------------------------------------


def test_json_creates_file(full_report: FreezeReport, tmp_path: Path) -> None:
    dest = tmp_path / "reports" / "freeze.json"
    JsonWriter().write(full_report, dest)
    assert dest.exists()


def test_json_creates_parent_dirs(full_report: FreezeReport, tmp_path: Path) -> None:
    dest = tmp_path / "a" / "b" / "freeze.json"
    JsonWriter().write(full_report, dest)
    assert dest.exists()


def test_json_is_valid(full_report: FreezeReport, tmp_path: Path) -> None:
    dest = tmp_path / "freeze.json"
    JsonWriter().write(full_report, dest)
    data = json.loads(dest.read_text(encoding="utf-8"))
    assert isinstance(data, dict)


def test_json_schema_version(full_report: FreezeReport, tmp_path: Path) -> None:
    dest = tmp_path / "freeze.json"
    JsonWriter().write(full_report, dest)
    data = json.loads(dest.read_text(encoding="utf-8"))
    assert data["schema_version"] == "1.7.0"


def test_json_generated_at(full_report: FreezeReport, tmp_path: Path) -> None:
    dest = tmp_path / "freeze.json"
    JsonWriter().write(full_report, dest)
    data = json.loads(dest.read_text(encoding="utf-8"))
    assert data["generated_at"] == "2024-06-01T12:00:00+00:00"


def test_json_library_count(full_report: FreezeReport, tmp_path: Path) -> None:
    dest = tmp_path / "freeze.json"
    JsonWriter().write(full_report, dest)
    data = json.loads(dest.read_text(encoding="utf-8"))
    assert data["catalog"]["library_count"] == 3
    assert len(data["catalog"]["libraries"]) == 3


def test_json_libraries_sorted(full_report: FreezeReport, tmp_path: Path) -> None:
    dest = tmp_path / "freeze.json"
    JsonWriter().write(full_report, dest)
    data = json.loads(dest.read_text(encoding="utf-8"))
    aliases = [entry["alias"] for entry in data["catalog"]["libraries"]]
    assert aliases == sorted(aliases)


def test_json_library_fields(full_report: FreezeReport, tmp_path: Path) -> None:
    dest = tmp_path / "freeze.json"
    JsonWriter().write(full_report, dest)
    data = json.loads(dest.read_text(encoding="utf-8"))
    lib = next(e for e in data["catalog"]["libraries"] if e["alias"] == "kotlin-stdlib")
    assert lib["group"] == "org.jetbrains.kotlin"
    assert lib["artifact"] == "kotlin-stdlib"
    assert lib["version"] == "2.0.0"
    assert lib["stability"] == "stable"


def test_json_plugin_fields(full_report: FreezeReport, tmp_path: Path) -> None:
    dest = tmp_path / "freeze.json"
    JsonWriter().write(full_report, dest)
    data = json.loads(dest.read_text(encoding="utf-8"))
    plugin = next(p for p in data["catalog"]["plugins"] if p["alias"] == "agp")
    assert plugin["id"] == "com.android.application"
    assert plugin["version"] == "8.3.0-rc02"
    assert plugin["stability"] == "rc"


def test_json_bundle_members_sorted(full_report: FreezeReport, tmp_path: Path) -> None:
    dest = tmp_path / "freeze.json"
    JsonWriter().write(full_report, dest)
    data = json.loads(dest.read_text(encoding="utf-8"))
    bundle = data["catalog"]["bundles"][0]
    assert bundle["alias"] == "compose"
    assert bundle["members"] == sorted(bundle["members"])


def test_json_ends_with_newline(full_report: FreezeReport, tmp_path: Path) -> None:
    dest = tmp_path / "freeze.json"
    JsonWriter().write(full_report, dest)
    assert dest.read_text(encoding="utf-8").endswith("\n")


# ---------------------------------------------------------------------------
# JsonWriter — rich-version metadata (RFC-0020)
# ---------------------------------------------------------------------------


def test_json_omits_version_constraints_when_absent(
    full_report: FreezeReport, tmp_path: Path
) -> None:
    """Libraries built with plain-string versions emit no ``version_constraints``."""
    dest = tmp_path / "freeze.json"
    JsonWriter().write(full_report, dest)
    data = json.loads(dest.read_text(encoding="utf-8"))
    for lib in data["catalog"]["libraries"]:
        assert "version_constraints" not in lib


def test_json_emits_version_constraints_when_present(tmp_path: Path) -> None:
    """A rich-versioned library serialises its declared keys verbatim."""
    catalog = Catalog(
        source_path=tmp_path / "libs.versions.toml",
        libraries=(
            Library(
                alias="kotlin-stdlib",
                group="org.jetbrains.kotlin",
                artifact="kotlin-stdlib",
                version=MavenVersion("2.0.0"),
                version_constraints=RichVersion(strictly="2.0.0", reject=("1.9.0",)),
            ),
        ),
        plugins=(),
        bundles=(),
    )
    report = FreezeReport(catalog=catalog, generated_at=_TS)

    dest = tmp_path / "freeze.json"
    JsonWriter().write(report, dest)
    data = json.loads(dest.read_text(encoding="utf-8"))

    lib = data["catalog"]["libraries"][0]
    assert lib["version"] == "2.0.0"
    assert lib["version_constraints"] == {
        "strictly": "2.0.0",
        "reject": ["1.9.0"],
    }


def test_json_reject_only_library_emits_empty_version_string(tmp_path: Path) -> None:
    """Reject-only entries serialise with an empty ``version`` and a non-empty ``reject``."""
    catalog = Catalog(
        source_path=tmp_path / "libs.versions.toml",
        libraries=(
            Library(
                alias="coil",
                group="io.coil-kt",
                artifact="coil-compose",
                version=MavenVersion(""),
                version_constraints=RichVersion(reject=("2.5.0", "2.5.0-rc1")),
            ),
        ),
        plugins=(),
        bundles=(),
    )
    report = FreezeReport(catalog=catalog, generated_at=_TS)

    dest = tmp_path / "freeze.json"
    JsonWriter().write(report, dest)
    data = json.loads(dest.read_text(encoding="utf-8"))

    lib = data["catalog"]["libraries"][0]
    assert lib["version"] == ""
    assert lib["version_constraints"] == {"reject": ["2.5.0", "2.5.0-rc1"]}


def test_json_empty_catalog(empty_report: FreezeReport, tmp_path: Path) -> None:
    dest = tmp_path / "freeze.json"
    JsonWriter().write(empty_report, dest)
    data = json.loads(dest.read_text(encoding="utf-8"))
    assert data["catalog"]["library_count"] == 0
    assert data["catalog"]["libraries"] == []
    assert data["catalog"]["plugins"] == []
    assert data["catalog"]["bundles"] == []


# ---------------------------------------------------------------------------
# Health findings — Markdown
# ---------------------------------------------------------------------------

_FINDING = Finding(
    rule_id="catalog.missing-plugins",
    severity=Severity.WARNING,
    message="No [plugins] section found",
    details="Add a [plugins] section.",
)


@pytest.fixture()
def report_with_findings(full_report: FreezeReport) -> FreezeReport:
    from dataclasses import replace

    return replace(full_report, health_findings=(_FINDING,))


def test_markdown_contains_health_section_when_findings_present(
    report_with_findings: FreezeReport, tmp_path: Path
) -> None:
    dest = tmp_path / "freeze.md"
    MarkdownWriter().write(report_with_findings, dest)
    assert "## Catalog Health" in dest.read_text(encoding="utf-8")


def test_markdown_health_section_contains_rule_id(
    report_with_findings: FreezeReport, tmp_path: Path
) -> None:
    dest = tmp_path / "freeze.md"
    MarkdownWriter().write(report_with_findings, dest)
    assert "catalog.missing-plugins" in dest.read_text(encoding="utf-8")


def test_markdown_renders_catalog_health_section_when_no_findings(
    full_report: FreezeReport, tmp_path: Path
) -> None:
    """RFC-0028: Catalog Health is unconditionally rendered with a
    "no findings" placeholder rather than elided when empty, so readers
    can distinguish "scanned, clean" from "skipped"."""
    dest = tmp_path / "freeze.md"
    MarkdownWriter().write(full_report, dest)
    content = dest.read_text(encoding="utf-8")
    assert "## Catalog Health" in content
    assert "No catalog health issues detected" in content


# ---------------------------------------------------------------------------
# Health findings — JSON
# ---------------------------------------------------------------------------


def test_json_health_section_present(full_report: FreezeReport, tmp_path: Path) -> None:
    dest = tmp_path / "freeze.json"
    JsonWriter().write(full_report, dest)
    data = json.loads(dest.read_text(encoding="utf-8"))
    assert "health" in data
    assert data["health"]["finding_count"] == 0
    assert data["health"]["findings"] == []


def test_json_health_finding_fields(report_with_findings: FreezeReport, tmp_path: Path) -> None:
    dest = tmp_path / "freeze.json"
    JsonWriter().write(report_with_findings, dest)
    data = json.loads(dest.read_text(encoding="utf-8"))
    finding = data["health"]["findings"][0]
    assert finding["rule_id"] == "catalog.missing-plugins"
    assert finding["severity"] == "warning"
    assert finding["message"] == "No [plugins] section found"
    assert finding["details"] == "Add a [plugins] section."


def test_json_finding_omits_details_when_empty(full_report: FreezeReport, tmp_path: Path) -> None:
    from dataclasses import replace

    no_details = Finding(rule_id="catalog.x", severity=Severity.INFO, message="m")
    report = replace(full_report, health_findings=(no_details,))
    dest = tmp_path / "freeze.json"
    JsonWriter().write(report, dest)
    data = json.loads(dest.read_text(encoding="utf-8"))
    assert "details" not in data["health"]["findings"][0]


def test_json_health_finding_count_matches_list(
    report_with_findings: FreezeReport, tmp_path: Path
) -> None:
    dest = tmp_path / "freeze.json"
    JsonWriter().write(report_with_findings, dest)
    data = json.loads(dest.read_text(encoding="utf-8"))
    assert data["health"]["finding_count"] == len(data["health"]["findings"])


# ---------------------------------------------------------------------------
# Markdown — Active Rejections section (RFC-0020 PR #2)
# ---------------------------------------------------------------------------


def _report_with_rejecting_library(tmp_path: Path) -> FreezeReport:
    catalog = Catalog(
        source_path=tmp_path / "libs.versions.toml",
        libraries=(
            Library(
                alias="coil-compose",
                group="io.coil-kt",
                artifact="coil-compose",
                version=MavenVersion(""),
                version_constraints=RichVersion(reject=("2.5.0", "2.5.0-rc1")),
            ),
            Library(
                alias="kotlin-stdlib",
                group="org.jetbrains.kotlin",
                artifact="kotlin-stdlib",
                version=MavenVersion("2.0.0"),
                version_constraints=RichVersion(strictly="2.0.0", reject=("1.9.0",)),
            ),
            Library(
                alias="plain",
                group="org.example",
                artifact="plain",
                version=MavenVersion("1.0.0"),
            ),
        ),
        plugins=(),
        bundles=(),
    )
    return FreezeReport(catalog=catalog, generated_at=_TS)


def test_markdown_active_rejections_section_present(tmp_path: Path) -> None:
    """Libraries with ``reject`` produce a dedicated section."""
    report = _report_with_rejecting_library(tmp_path)
    dest = tmp_path / "freeze.md"
    MarkdownWriter().write(report, dest)
    text = dest.read_text(encoding="utf-8")
    assert "## Active Rejections" in text


def test_markdown_active_rejections_lists_rejected_versions(tmp_path: Path) -> None:
    """Every rejected version appears verbatim in the table."""
    report = _report_with_rejecting_library(tmp_path)
    dest = tmp_path / "freeze.md"
    MarkdownWriter().write(report, dest)
    text = dest.read_text(encoding="utf-8")
    assert "2.5.0" in text
    assert "2.5.0-rc1" in text
    assert "1.9.0" in text


def test_markdown_active_rejections_lists_aliases(tmp_path: Path) -> None:
    """Each rejecting library appears as its own row."""
    report = _report_with_rejecting_library(tmp_path)
    dest = tmp_path / "freeze.md"
    MarkdownWriter().write(report, dest)
    text = dest.read_text(encoding="utf-8")
    # Both rejecting libraries are listed; the plain library is not.
    rejections_section = text.split("## Active Rejections", 1)[1]
    next_section = rejections_section.split("\n## ", 1)[0]
    assert "coil-compose" in next_section
    assert "kotlin-stdlib" in next_section
    assert "plain" not in next_section


def test_markdown_omits_active_rejections_when_no_library_uses_reject(
    full_report: FreezeReport, tmp_path: Path
) -> None:
    """No reject lists → no section emitted (keeps reports lean)."""
    dest = tmp_path / "freeze.md"
    MarkdownWriter().write(full_report, dest)
    text = dest.read_text(encoding="utf-8")
    assert "Active Rejections" not in text


def test_markdown_active_rejections_singular_noun(tmp_path: Path) -> None:
    """Header agrees in number when exactly one library declares a reject list."""
    catalog = Catalog(
        source_path=tmp_path / "libs.versions.toml",
        libraries=(
            Library(
                alias="coil",
                group="io.coil-kt",
                artifact="coil",
                version=MavenVersion(""),
                version_constraints=RichVersion(reject=("2.5.0",)),
            ),
        ),
        plugins=(),
        bundles=(),
    )
    report = FreezeReport(catalog=catalog, generated_at=_TS)
    dest = tmp_path / "freeze.md"
    MarkdownWriter().write(report, dest)
    text = dest.read_text(encoding="utf-8")
    assert "Active Rejections (1 rejection)" in text


# ---------------------------------------------------------------------------
# RFC-0028 — empty-section placeholders + security scanned distinction
# ---------------------------------------------------------------------------


def test_markdown_security_section_renders_not_configured_when_scanner_absent(
    full_report: FreezeReport, tmp_path: Path
) -> None:
    """No scanner injected → MD must show the remediation placeholder.

    Pre-fix the section elided entirely, making the report look
    identical to a clean security scan.
    """
    dest = tmp_path / "freeze.md"
    MarkdownWriter().write(full_report, dest)  # security_scanned defaults to False
    text = dest.read_text(encoding="utf-8")
    assert "## Security" in text
    assert "scan not configured" in text
    assert "GITHUB_TOKEN" in text


def test_markdown_security_section_renders_clean_when_scanned_no_findings(
    tmp_path: Path,
) -> None:
    """Scanner injected and ran with zero advisories → clean placeholder."""
    catalog = Catalog(
        source_path=tmp_path / "libs.versions.toml",
        libraries=(Library("lib", "g", "art", MavenVersion("1.0.0")),),
        plugins=(),
        bundles=(),
    )
    report = FreezeReport(catalog=catalog, generated_at=_TS, security_scanned=True)
    dest = tmp_path / "freeze.md"
    MarkdownWriter().write(report, dest)
    text = dest.read_text(encoding="utf-8")
    assert "## Security" in text
    assert "No known security advisories" in text
    assert "GITHUB_TOKEN" not in text


def test_markdown_compliance_section_renders_placeholder_when_empty(
    full_report: FreezeReport, tmp_path: Path
) -> None:
    dest = tmp_path / "freeze.md"
    MarkdownWriter().write(full_report, dest)
    text = dest.read_text(encoding="utf-8")
    assert "## Play Store Compliance" in text
    assert "No Play Store compliance issues found" in text


def test_markdown_toolchain_section_renders_placeholder_when_empty(
    full_report: FreezeReport, tmp_path: Path
) -> None:
    dest = tmp_path / "freeze.md"
    MarkdownWriter().write(full_report, dest)
    text = dest.read_text(encoding="utf-8")
    assert "## Toolchain Compatibility" in text
    assert "No toolchain compatibility issues detected" in text


def test_markdown_library_health_section_renders_placeholder_when_empty(
    full_report: FreezeReport, tmp_path: Path
) -> None:
    dest = tmp_path / "freeze.md"
    MarkdownWriter().write(full_report, dest)
    text = dest.read_text(encoding="utf-8")
    assert "## Library Health" in text
    assert "No deprecation, relocation, or inactivity signals detected" in text


def test_markdown_changelog_section_renders_placeholder_when_empty(
    full_report: FreezeReport, tmp_path: Path
) -> None:
    dest = tmp_path / "freeze.md"
    MarkdownWriter().write(full_report, dest)
    text = dest.read_text(encoding="utf-8")
    assert "## Major Upgrades" in text
    assert "No major upgrades available" in text


def test_json_security_scanned_source_is_authoritative_flag(tmp_path: Path) -> None:
    """RFC-0028: json security.scanned now reflects the use-case flag,
    not the ``len(security_advisories) > 0`` heuristic."""
    catalog = Catalog(
        source_path=tmp_path / "libs.versions.toml",
        libraries=(Library("lib", "g", "art", MavenVersion("1.0.0")),),
        plugins=(),
        bundles=(),
    )
    # Scanner ran on a catalog where no library produced advisories
    # (degenerate "all-clean" case that pre-RFC reported scanned=false).
    report = FreezeReport(catalog=catalog, generated_at=_TS, security_scanned=True)
    dest = tmp_path / "freeze.json"
    JsonWriter().write(report, dest)
    data = json.loads(dest.read_text(encoding="utf-8"))
    assert data["security"]["scanned"] is True
    assert data["security"]["vulnerable_count"] == 0


def test_json_security_scanned_false_when_flag_default(tmp_path: Path) -> None:
    catalog = Catalog(
        source_path=tmp_path / "libs.versions.toml",
        libraries=(Library("lib", "g", "art", MavenVersion("1.0.0")),),
        plugins=(),
        bundles=(),
    )
    report = FreezeReport(catalog=catalog, generated_at=_TS)  # security_scanned defaults False
    dest = tmp_path / "freeze.json"
    JsonWriter().write(report, dest)
    data = json.loads(dest.read_text(encoding="utf-8"))
    assert data["security"]["scanned"] is False
