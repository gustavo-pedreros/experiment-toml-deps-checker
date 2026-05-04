"""Unit tests for SlackWriter."""

from __future__ import annotations

import json
from pathlib import Path

from gradle_deps_monitor.domain import FreezeReport
from gradle_deps_monitor.domain.catalog import Catalog, Library, Plugin
from gradle_deps_monitor.domain.finding import Finding, Severity
from gradle_deps_monitor.domain.version import MavenVersion
from gradle_deps_monitor.infrastructure.writers.slack_writer import SlackWriter

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_catalog(
    *,
    libraries: tuple[Library, ...] = (),
    plugins: tuple[Plugin, ...] = (),
    bundles: tuple[str, ...] = (),
    source_name: str = "libs.versions.toml",
    tmp_path: Path,
) -> Catalog:
    return Catalog(
        source_path=tmp_path / source_name,
        libraries=libraries,
        plugins=plugins,
        bundles=bundles,
    )


def _stable_lib(alias: str, version: str, tmp_path: Path) -> Library:
    return Library(
        alias=alias,
        group="com.example",
        artifact=alias,
        version=MavenVersion(version),
    )


def _alpha_lib(alias: str, tmp_path: Path) -> Library:
    return Library(
        alias=alias,
        group="com.example",
        artifact=alias,
        version=MavenVersion("1.0.0-alpha01"),
    )


# ---------------------------------------------------------------------------
# File creation
# ---------------------------------------------------------------------------


def test_write_creates_file(tmp_path: Path) -> None:
    catalog = _make_catalog(tmp_path=tmp_path)
    report = FreezeReport(catalog=catalog)
    dest = tmp_path / "out" / "freeze-slack.json"

    SlackWriter().write(report, dest)

    assert dest.exists()


def test_write_creates_parent_directories(tmp_path: Path) -> None:
    catalog = _make_catalog(tmp_path=tmp_path)
    report = FreezeReport(catalog=catalog)
    dest = tmp_path / "a" / "b" / "c" / "slack.json"

    SlackWriter().write(report, dest)

    assert dest.exists()


def test_write_output_ends_with_newline(tmp_path: Path) -> None:
    catalog = _make_catalog(tmp_path=tmp_path)
    report = FreezeReport(catalog=catalog)
    dest = tmp_path / "freeze-slack.json"

    SlackWriter().write(report, dest)

    assert dest.read_text(encoding="utf-8").endswith("\n")


# ---------------------------------------------------------------------------
# JSON validity & top-level structure
# ---------------------------------------------------------------------------


def test_write_produces_valid_json(tmp_path: Path) -> None:
    catalog = _make_catalog(tmp_path=tmp_path)
    report = FreezeReport(catalog=catalog)
    dest = tmp_path / "freeze-slack.json"

    SlackWriter().write(report, dest)

    data = json.loads(dest.read_text(encoding="utf-8"))
    assert isinstance(data, dict)


def test_payload_has_blocks_key(tmp_path: Path) -> None:
    catalog = _make_catalog(tmp_path=tmp_path)
    report = FreezeReport(catalog=catalog)
    dest = tmp_path / "freeze-slack.json"

    SlackWriter().write(report, dest)

    data = json.loads(dest.read_text(encoding="utf-8"))
    assert "blocks" in data
    assert isinstance(data["blocks"], list)


def test_blocks_list_is_not_empty(tmp_path: Path) -> None:
    catalog = _make_catalog(tmp_path=tmp_path)
    report = FreezeReport(catalog=catalog)
    dest = tmp_path / "freeze-slack.json"

    SlackWriter().write(report, dest)

    data = json.loads(dest.read_text(encoding="utf-8"))
    assert len(data["blocks"]) > 0


# ---------------------------------------------------------------------------
# Header block
# ---------------------------------------------------------------------------


def test_first_block_is_header(tmp_path: Path) -> None:
    catalog = _make_catalog(tmp_path=tmp_path)
    report = FreezeReport(catalog=catalog)
    dest = tmp_path / "freeze-slack.json"

    SlackWriter().write(report, dest)

    data = json.loads(dest.read_text(encoding="utf-8"))
    assert data["blocks"][0]["type"] == "header"


def test_header_block_contains_report_title(tmp_path: Path) -> None:
    catalog = _make_catalog(tmp_path=tmp_path)
    report = FreezeReport(catalog=catalog)
    dest = tmp_path / "freeze-slack.json"

    SlackWriter().write(report, dest)

    data = json.loads(dest.read_text(encoding="utf-8"))
    header_text = data["blocks"][0]["text"]["text"]
    assert "Gradle Dependency Freeze Report" in header_text


# ---------------------------------------------------------------------------
# Stats block — library / plugin / bundle counts
# ---------------------------------------------------------------------------


def test_stats_block_shows_library_count(tmp_path: Path) -> None:
    libs = (
        _stable_lib("core-ktx", "1.13.0", tmp_path),
        _stable_lib("appcompat", "1.7.0", tmp_path),
    )
    catalog = _make_catalog(libraries=libs, tmp_path=tmp_path)
    report = FreezeReport(catalog=catalog)
    dest = tmp_path / "freeze-slack.json"

    SlackWriter().write(report, dest)

    raw = dest.read_text(encoding="utf-8")
    assert "2" in raw  # library count appears somewhere


def test_stats_block_shows_plugin_count(tmp_path: Path) -> None:
    plugins = (
        Plugin(
            alias="kotlin-android", id="org.jetbrains.kotlin.android", version=MavenVersion("2.0.0")
        ),
    )
    catalog = _make_catalog(plugins=plugins, tmp_path=tmp_path)
    report = FreezeReport(catalog=catalog)
    dest = tmp_path / "freeze-slack.json"

    SlackWriter().write(report, dest)

    raw = dest.read_text(encoding="utf-8")
    assert "1" in raw  # plugin count appears somewhere


# ---------------------------------------------------------------------------
# Non-stable versions block
# ---------------------------------------------------------------------------


def test_non_stable_block_absent_when_all_stable(tmp_path: Path) -> None:
    libs = (_stable_lib("core-ktx", "1.13.0", tmp_path),)
    catalog = _make_catalog(libraries=libs, tmp_path=tmp_path)
    report = FreezeReport(catalog=catalog)
    dest = tmp_path / "freeze-slack.json"

    SlackWriter().write(report, dest)

    raw = dest.read_text(encoding="utf-8")
    assert "Non-stable" not in raw


def test_non_stable_block_present_when_alpha_lib(tmp_path: Path) -> None:
    libs = (_alpha_lib("my-alpha-lib", tmp_path),)
    catalog = _make_catalog(libraries=libs, tmp_path=tmp_path)
    report = FreezeReport(catalog=catalog)
    dest = tmp_path / "freeze-slack.json"

    SlackWriter().write(report, dest)

    raw = dest.read_text(encoding="utf-8")
    assert "Non-stable" in raw
    assert "my-alpha-lib" in raw


def test_non_stable_block_truncates_at_ten(tmp_path: Path) -> None:
    libs = tuple(_alpha_lib(f"lib-{i:02d}", tmp_path) for i in range(12))
    catalog = _make_catalog(libraries=libs, tmp_path=tmp_path)
    report = FreezeReport(catalog=catalog)
    dest = tmp_path / "freeze-slack.json"

    SlackWriter().write(report, dest)

    raw = dest.read_text(encoding="utf-8")
    assert "2 more" in raw  # truncation indicator


# ---------------------------------------------------------------------------
# Health block
# ---------------------------------------------------------------------------


def test_health_block_shows_checkmark_when_clean(tmp_path: Path) -> None:
    catalog = _make_catalog(tmp_path=tmp_path)
    report = FreezeReport(catalog=catalog, health_findings=())
    dest = tmp_path / "freeze-slack.json"

    SlackWriter().write(report, dest)

    raw = dest.read_text(encoding="utf-8")
    assert "white_check_mark" in raw


def test_health_block_shows_findings_when_present(tmp_path: Path) -> None:
    findings = (
        Finding(rule_id="HDX-001", severity=Severity.ERROR, message="duplicate library detected"),
    )
    catalog = _make_catalog(tmp_path=tmp_path)
    report = FreezeReport(catalog=catalog, health_findings=findings)
    dest = tmp_path / "freeze-slack.json"

    SlackWriter().write(report, dest)

    raw = dest.read_text(encoding="utf-8")
    assert "HDX-001" in raw
    assert "duplicate library detected" in raw


def test_health_block_shows_error_emoji_for_error_severity(tmp_path: Path) -> None:
    findings = (Finding(rule_id="HDX-001", severity=Severity.ERROR, message="some error"),)
    catalog = _make_catalog(tmp_path=tmp_path)
    report = FreezeReport(catalog=catalog, health_findings=findings)
    dest = tmp_path / "freeze-slack.json"

    SlackWriter().write(report, dest)

    raw = dest.read_text(encoding="utf-8")
    assert "red_circle" in raw


def test_health_block_shows_warning_emoji_for_warning_severity(tmp_path: Path) -> None:
    findings = (Finding(rule_id="HDX-002", severity=Severity.WARNING, message="some warning"),)
    catalog = _make_catalog(tmp_path=tmp_path)
    report = FreezeReport(catalog=catalog, health_findings=findings)
    dest = tmp_path / "freeze-slack.json"

    SlackWriter().write(report, dest)

    raw = dest.read_text(encoding="utf-8")
    assert "warning" in raw


def test_health_block_shows_finding_count(tmp_path: Path) -> None:
    findings = (
        Finding(rule_id="HDX-001", severity=Severity.ERROR, message="error one"),
        Finding(rule_id="HDX-002", severity=Severity.WARNING, message="warning one"),
    )
    catalog = _make_catalog(tmp_path=tmp_path)
    report = FreezeReport(catalog=catalog, health_findings=findings)
    dest = tmp_path / "freeze-slack.json"

    SlackWriter().write(report, dest)

    raw = dest.read_text(encoding="utf-8")
    assert "2 finding" in raw
