"""Tests for MarkdownWriter and JsonWriter."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from gradle_deps_monitor.domain import Bundle, Catalog, FreezeReport, Library, Plugin
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
    assert data["schema_version"] == "1"


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


def test_json_empty_catalog(empty_report: FreezeReport, tmp_path: Path) -> None:
    dest = tmp_path / "freeze.json"
    JsonWriter().write(empty_report, dest)
    data = json.loads(dest.read_text(encoding="utf-8"))
    assert data["catalog"]["library_count"] == 0
    assert data["catalog"]["libraries"] == []
    assert data["catalog"]["plugins"] == []
    assert data["catalog"]["bundles"] == []
