"""Cross-writer severity unification tests (RFC-0016b).

Locks in the success metric: the same finding severity must render with the
same emoji across the Markdown writer, the Slack writer, and the JSON writer.
A regression that diverges them (e.g. someone adding a private style dict
back into a section) breaks these assertions.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from gradle_deps_monitor.domain import FreezeReport
from gradle_deps_monitor.domain.advisory import (
    Advisory,
    AdvisorySeverity,
    LibraryAdvisory,
)
from gradle_deps_monitor.domain.catalog import Catalog, Library
from gradle_deps_monitor.domain.compliance import ComplianceFinding, ComplianceSeverity
from gradle_deps_monitor.domain.finding import Finding, Severity
from gradle_deps_monitor.domain.library_health import (
    HealthSignal,
    LibraryHealthFinding,
    LibraryHealthSeverity,
)
from gradle_deps_monitor.domain.severity import CommonSeverity
from gradle_deps_monitor.domain.severity_style import style_for
from gradle_deps_monitor.domain.toolchain import ToolchainFinding, ToolchainSeverity
from gradle_deps_monitor.domain.version import MavenVersion
from gradle_deps_monitor.infrastructure.writers.json_writer import JsonWriter
from gradle_deps_monitor.infrastructure.writers.markdown_writer import MarkdownWriter
from gradle_deps_monitor.infrastructure.writers.slack_writer import SlackWriter

# An ERROR-flavoured value from each section. They all map to
# CommonSeverity.ERROR via to_common(); RFC-0016b says they must render
# identically.
_ERROR_FIXTURES: tuple[tuple[str, str], ...] = (
    ("catalog", Severity.ERROR.value),
    ("library_health", LibraryHealthSeverity.HIGH.value),
    ("compliance", ComplianceSeverity.ERROR.value),
    ("toolchain", ToolchainSeverity.ERROR.value),
    ("advisory", AdvisorySeverity.CRITICAL.value),
)


def _catalog(tmp_path: Path) -> Catalog:
    toml = tmp_path / "libs.versions.toml"
    toml.write_text("[versions]\n[libraries]\n", encoding="utf-8")
    return Catalog(
        source_path=toml,
        libraries=(
            Library(
                alias="x",
                group="com.example",
                artifact="x",
                version=MavenVersion("1.0.0"),
            ),
        ),
        plugins=(),
        bundles=(),
    )


def _report_with_one_error_per_section(tmp_path: Path) -> FreezeReport:
    """Build a report containing exactly one ERROR-flavoured finding per section."""
    return FreezeReport(
        catalog=_catalog(tmp_path),
        generated_at=datetime(2026, 5, 7, 10, 0, 0, tzinfo=UTC),
        health_findings=(
            Finding(rule_id="HDX-001", severity=Severity.ERROR, message="duplicate library"),
        ),
        compliance_findings=(
            ComplianceFinding(
                rule_id="PLAY-DEP-001",
                severity=ComplianceSeverity.ERROR,
                message="SafetyNet deprecated",
                alias="safetynet",
            ),
        ),
        toolchain_findings=(
            ToolchainFinding(
                rule_id="TOOL-KC-001",
                severity=ToolchainSeverity.ERROR,
                message="Kotlin/Compose mismatch",
            ),
        ),
        library_health_findings=(
            LibraryHealthFinding(
                alias="butterknife",
                coordinate="com.jakewharton:butterknife",
                version="10.2.3",
                signal=HealthSignal.CURATED,
                severity=LibraryHealthSeverity.HIGH,
                message="deprecated",
            ),
        ),
        security_advisories=(
            LibraryAdvisory(
                alias="x",
                coordinate="com.example:x",
                version="1.0.0",
                advisories=(
                    Advisory(
                        ghsa_id="GHSA-xxxx-yyyy-zzzz",
                        cve_id="CVE-2024-0001",
                        severity=AdvisorySeverity.CRITICAL,
                        summary="critical issue",
                        fixed_version="1.1.0",
                        url="https://example.com",
                        source="github",
                    ),
                ),
            ),
        ),
    )


def test_markdown_uses_unified_error_emoji_in_every_section(tmp_path: Path) -> None:
    """Every section's ERROR-equivalent renders as the unified ERROR emoji."""
    report = _report_with_one_error_per_section(tmp_path)
    dest = tmp_path / "freeze.md"
    MarkdownWriter().write(report, dest)
    text = dest.read_text(encoding="utf-8")

    expected_emoji = style_for(CommonSeverity.ERROR).md_emoji
    # Five sections, one ERROR each: at least five occurrences of the unified
    # emoji. Asserting on the count proves no section silently fell back to a
    # different emoji.
    assert text.count(expected_emoji) >= len(_ERROR_FIXTURES)


def test_slack_uses_unified_error_emoji_in_every_section(tmp_path: Path) -> None:
    report = _report_with_one_error_per_section(tmp_path)
    dest = tmp_path / "freeze-slack.json"
    SlackWriter().write(report, dest)
    raw = dest.read_text(encoding="utf-8")

    expected_emoji = style_for(CommonSeverity.ERROR).slack_emoji
    assert raw.count(expected_emoji) >= len(_ERROR_FIXTURES)


def test_json_emits_common_severity_on_every_finding(tmp_path: Path) -> None:
    """All finding-shaped objects expose ``common_severity`` (schema 1.7.0)."""
    report = _report_with_one_error_per_section(tmp_path)
    dest = tmp_path / "freeze.json"
    JsonWriter().write(report, dest)
    data = json.loads(dest.read_text(encoding="utf-8"))

    assert data["schema_version"] == "1.7.0"

    # Every finding-shaped object now has common_severity = "error".
    assert data["health"]["findings"][0]["common_severity"] == "error"
    assert data["compliance"]["findings"][0]["common_severity"] == "error"
    assert data["toolchain"]["findings"][0]["common_severity"] == "error"
    assert data["library_health"]["findings"][0]["common_severity"] == "error"
    advisory = data["security"]["libraries"][0]["advisories"][0]
    assert advisory["common_severity"] == "error"


def test_no_legacy_emoji_dicts_remain_in_writers() -> None:
    """Defensive: catch the regression of bringing back per-section style dicts.

    These names were the historical private dicts (RFC-0016b retired them).
    Re-introducing one would silently re-fragment the rendering.
    """
    from gradle_deps_monitor.infrastructure.writers import (
        markdown_writer,
        slack_writer,
    )

    forbidden = {
        "_SEVERITY_ICON",
        "_ADVISORY_SEVERITY_ICON",
        "_COMPLIANCE_SEVERITY_ICON",
        "_TOOLCHAIN_SEVERITY_ICON",
        "_LIBRARY_HEALTH_SEVERITY_ICON",
        "_SEVERITY_EMOJI",
        "_ADVISORY_EMOJI",
        "_COMPLIANCE_EMOJI",
        "_TOOLCHAIN_EMOJI",
        "_LIBRARY_HEALTH_EMOJI",
    }
    for module in (markdown_writer, slack_writer):
        for name in forbidden:
            assert not hasattr(module, name), (
                f"{module.__name__}.{name} re-introduced; use severity_style.STYLE instead"
            )
