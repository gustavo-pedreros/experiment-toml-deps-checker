"""Unit tests for DiffMarkdownWriter, DiffJsonWriter, DiffSlackWriter."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from gradle_deps_monitor.domain.diff import (
    FindingChange,
    FreezeDiff,
    LibraryChange,
    PluginChange,
    VersionBump,
)
from gradle_deps_monitor.infrastructure.writers.diff_json_writer import DiffJsonWriter
from gradle_deps_monitor.infrastructure.writers.diff_markdown_writer import DiffMarkdownWriter
from gradle_deps_monitor.infrastructure.writers.diff_slack_writer import DiffSlackWriter

_BEFORE_TS = datetime(2026, 4, 18, 10, 0, 0, tzinfo=UTC)
_AFTER_TS = datetime(2026, 5, 4, 10, 0, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _lib(
    alias: str, before: str | None, after: str | None, bump: VersionBump | None
) -> LibraryChange:
    return LibraryChange(
        alias=alias,
        coordinate=f"com.example:{alias}",
        before_version=before,
        after_version=after,
        bump=bump,
    )


def _plugin(
    alias: str, before: str | None, after: str | None, bump: VersionBump | None
) -> PluginChange:
    return PluginChange(
        alias=alias,
        plugin_id=f"org.example.{alias}",
        before_version=before,
        after_version=after,
        bump=bump,
    )


def _finding(rule_id: str, status: str) -> FindingChange:
    return FindingChange(
        rule_id=rule_id, severity="warning", message=f"{rule_id} msg", status=status
    )  # type: ignore[arg-type]


@pytest.fixture()
def empty_diff() -> FreezeDiff:
    return FreezeDiff(
        before_generated_at=_BEFORE_TS,
        after_generated_at=_AFTER_TS,
        library_changes=(),
        plugin_changes=(),
        finding_changes=(),
    )


@pytest.fixture()
def rich_diff() -> FreezeDiff:
    return FreezeDiff(
        before_generated_at=_BEFORE_TS,
        after_generated_at=_AFTER_TS,
        library_changes=(
            _lib("major-lib", "1.0.0", "2.0.0", VersionBump.MAJOR),
            _lib("minor-lib", "1.0.0", "1.1.0", VersionBump.MINOR),
            _lib("added-lib", None, "1.0.0", None),
            _lib("removed-lib", "1.0.0", None, None),
        ),
        plugin_changes=(_plugin("kotlin-android", "1.9.0", "2.0.0", VersionBump.MAJOR),),
        finding_changes=(
            _finding("HDX-001", "introduced"),
            _finding("HDX-002", "resolved"),
        ),
    )


@pytest.fixture()
def baseline_diff() -> FreezeDiff:
    return FreezeDiff(
        before_generated_at=None,
        after_generated_at=_AFTER_TS,
        library_changes=(),
        plugin_changes=(),
        finding_changes=(),
        is_baseline=True,
    )


# ===========================================================================
# DiffMarkdownWriter
# ===========================================================================


class TestDiffMarkdownWriter:
    _writer = DiffMarkdownWriter()

    def test_creates_file(self, tmp_path: Path, empty_diff: FreezeDiff) -> None:
        dest = tmp_path / "freeze-diff.md"
        self._writer.write(empty_diff, dest)
        assert dest.exists()

    def test_creates_parent_dirs(self, tmp_path: Path, empty_diff: FreezeDiff) -> None:
        dest = tmp_path / "a" / "b" / "diff.md"
        self._writer.write(empty_diff, dest)
        assert dest.exists()

    def test_ends_with_newline(self, tmp_path: Path, empty_diff: FreezeDiff) -> None:
        dest = tmp_path / "diff.md"
        self._writer.write(empty_diff, dest)
        assert dest.read_text(encoding="utf-8").endswith("\n")

    def test_diff_header_contains_dates(self, tmp_path: Path, rich_diff: FreezeDiff) -> None:
        dest = tmp_path / "diff.md"
        self._writer.write(rich_diff, dest)
        content = dest.read_text(encoding="utf-8")
        assert "2026-04-18" in content
        assert "2026-05-04" in content

    def test_diff_shows_major_section(self, tmp_path: Path, rich_diff: FreezeDiff) -> None:
        dest = tmp_path / "diff.md"
        self._writer.write(rich_diff, dest)
        content = dest.read_text(encoding="utf-8")
        assert "Major" in content
        assert "major-lib" in content

    def test_diff_shows_added_section(self, tmp_path: Path, rich_diff: FreezeDiff) -> None:
        dest = tmp_path / "diff.md"
        self._writer.write(rich_diff, dest)
        content = dest.read_text(encoding="utf-8")
        assert "Added" in content
        assert "added-lib" in content

    def test_diff_shows_removed_section(self, tmp_path: Path, rich_diff: FreezeDiff) -> None:
        dest = tmp_path / "diff.md"
        self._writer.write(rich_diff, dest)
        content = dest.read_text(encoding="utf-8")
        assert "Removed" in content
        assert "removed-lib" in content

    def test_diff_shows_plugins(self, tmp_path: Path, rich_diff: FreezeDiff) -> None:
        dest = tmp_path / "diff.md"
        self._writer.write(rich_diff, dest)
        content = dest.read_text(encoding="utf-8")
        assert "kotlin-android" in content

    def test_diff_shows_findings(self, tmp_path: Path, rich_diff: FreezeDiff) -> None:
        dest = tmp_path / "diff.md"
        self._writer.write(rich_diff, dest)
        content = dest.read_text(encoding="utf-8")
        assert "HDX-001" in content
        assert "HDX-002" in content
        assert "Introduced" in content
        assert "Resolved" in content

    def test_empty_diff_shows_no_changes(self, tmp_path: Path, empty_diff: FreezeDiff) -> None:
        dest = tmp_path / "diff.md"
        self._writer.write(empty_diff, dest)
        content = dest.read_text(encoding="utf-8")
        assert "No library changes" in content

    def test_baseline_shows_baseline_header(
        self, tmp_path: Path, baseline_diff: FreezeDiff
    ) -> None:
        dest = tmp_path / "diff.md"
        self._writer.write(baseline_diff, dest)
        content = dest.read_text(encoding="utf-8")
        assert "Baseline" in content
        assert "first registered freeze report" in content


# ===========================================================================
# DiffJsonWriter
# ===========================================================================


class TestDiffJsonWriter:
    _writer = DiffJsonWriter()

    def test_creates_file(self, tmp_path: Path, empty_diff: FreezeDiff) -> None:
        dest = tmp_path / "freeze-diff.json"
        self._writer.write(empty_diff, dest)
        assert dest.exists()

    def test_creates_parent_dirs(self, tmp_path: Path, empty_diff: FreezeDiff) -> None:
        dest = tmp_path / "a" / "b" / "diff.json"
        self._writer.write(empty_diff, dest)
        assert dest.exists()

    def test_ends_with_newline(self, tmp_path: Path, empty_diff: FreezeDiff) -> None:
        dest = tmp_path / "diff.json"
        self._writer.write(empty_diff, dest)
        assert dest.read_text(encoding="utf-8").endswith("\n")

    def test_produces_valid_json(self, tmp_path: Path, empty_diff: FreezeDiff) -> None:
        dest = tmp_path / "diff.json"
        self._writer.write(empty_diff, dest)
        data = json.loads(dest.read_text(encoding="utf-8"))
        assert isinstance(data, dict)

    def test_schema_version(self, tmp_path: Path, empty_diff: FreezeDiff) -> None:
        dest = tmp_path / "diff.json"
        self._writer.write(empty_diff, dest)
        data = json.loads(dest.read_text(encoding="utf-8"))
        assert data["schema_version"] == "1.0.0"

    def test_timestamps(self, tmp_path: Path, rich_diff: FreezeDiff) -> None:
        dest = tmp_path / "diff.json"
        self._writer.write(rich_diff, dest)
        data = json.loads(dest.read_text(encoding="utf-8"))
        assert "2026-04-18" in data["before_generated_at"]
        assert "2026-05-04" in data["after_generated_at"]

    def test_is_baseline_false_for_regular_diff(
        self, tmp_path: Path, rich_diff: FreezeDiff
    ) -> None:
        dest = tmp_path / "diff.json"
        self._writer.write(rich_diff, dest)
        data = json.loads(dest.read_text(encoding="utf-8"))
        assert data["is_baseline"] is False

    def test_is_baseline_true_for_baseline(self, tmp_path: Path, baseline_diff: FreezeDiff) -> None:
        dest = tmp_path / "diff.json"
        self._writer.write(baseline_diff, dest)
        data = json.loads(dest.read_text(encoding="utf-8"))
        assert data["is_baseline"] is True
        assert data["before_generated_at"] is None

    def test_summary_counts(self, tmp_path: Path, rich_diff: FreezeDiff) -> None:
        dest = tmp_path / "diff.json"
        self._writer.write(rich_diff, dest)
        data = json.loads(dest.read_text(encoding="utf-8"))
        summary = data["summary"]["libraries"]
        assert summary["major"] == 1
        assert summary["minor"] == 1
        assert summary["added"] == 1
        assert summary["removed"] == 1

    def test_upgraded_libraries_present(self, tmp_path: Path, rich_diff: FreezeDiff) -> None:
        dest = tmp_path / "diff.json"
        self._writer.write(rich_diff, dest)
        data = json.loads(dest.read_text(encoding="utf-8"))
        upgraded = data["libraries"]["upgraded"]
        aliases = [lib["alias"] for lib in upgraded]
        assert "major-lib" in aliases
        assert "minor-lib" in aliases

    def test_added_library_has_no_before(self, tmp_path: Path, rich_diff: FreezeDiff) -> None:
        dest = tmp_path / "diff.json"
        self._writer.write(rich_diff, dest)
        data = json.loads(dest.read_text(encoding="utf-8"))
        added = data["libraries"]["added"]
        assert len(added) == 1
        assert "before" not in added[0]
        assert added[0]["after"] == "1.0.0"

    def test_findings_introduced_and_resolved(self, tmp_path: Path, rich_diff: FreezeDiff) -> None:
        dest = tmp_path / "diff.json"
        self._writer.write(rich_diff, dest)
        data = json.loads(dest.read_text(encoding="utf-8"))
        assert len(data["findings"]["introduced"]) == 1
        assert len(data["findings"]["resolved"]) == 1
        assert data["findings"]["introduced"][0]["rule_id"] == "HDX-001"
        assert data["findings"]["resolved"][0]["rule_id"] == "HDX-002"


# ===========================================================================
# DiffSlackWriter
# ===========================================================================


class TestDiffSlackWriter:
    _writer = DiffSlackWriter()

    def test_creates_file(self, tmp_path: Path, empty_diff: FreezeDiff) -> None:
        dest = tmp_path / "freeze-diff-slack.json"
        self._writer.write(empty_diff, dest)
        assert dest.exists()

    def test_ends_with_newline(self, tmp_path: Path, empty_diff: FreezeDiff) -> None:
        dest = tmp_path / "diff-slack.json"
        self._writer.write(empty_diff, dest)
        assert dest.read_text(encoding="utf-8").endswith("\n")

    def test_produces_valid_json(self, tmp_path: Path, empty_diff: FreezeDiff) -> None:
        dest = tmp_path / "diff-slack.json"
        self._writer.write(empty_diff, dest)
        data = json.loads(dest.read_text(encoding="utf-8"))
        assert "blocks" in data

    def test_first_block_is_header(self, tmp_path: Path, rich_diff: FreezeDiff) -> None:
        dest = tmp_path / "diff-slack.json"
        self._writer.write(rich_diff, dest)
        data = json.loads(dest.read_text(encoding="utf-8"))
        assert data["blocks"][0]["type"] == "header"

    def test_header_contains_dates(self, tmp_path: Path, rich_diff: FreezeDiff) -> None:
        dest = tmp_path / "diff-slack.json"
        self._writer.write(rich_diff, dest)
        raw = dest.read_text(encoding="utf-8")
        assert "2026-04-18" in raw
        assert "2026-05-04" in raw

    def test_libraries_block_present_when_changes(
        self, tmp_path: Path, rich_diff: FreezeDiff
    ) -> None:
        dest = tmp_path / "diff-slack.json"
        self._writer.write(rich_diff, dest)
        raw = dest.read_text(encoding="utf-8")
        assert "major-lib" in raw

    def test_no_library_block_when_no_changes(self, tmp_path: Path, empty_diff: FreezeDiff) -> None:
        dest = tmp_path / "diff-slack.json"
        self._writer.write(empty_diff, dest)
        raw = dest.read_text(encoding="utf-8")
        # No library details when nothing changed
        assert "Major" not in raw

    def test_health_checkmark_when_no_finding_changes(
        self, tmp_path: Path, empty_diff: FreezeDiff
    ) -> None:
        dest = tmp_path / "diff-slack.json"
        self._writer.write(empty_diff, dest)
        raw = dest.read_text(encoding="utf-8")
        assert "white_check_mark" in raw

    def test_findings_shown_when_present(self, tmp_path: Path, rich_diff: FreezeDiff) -> None:
        dest = tmp_path / "diff-slack.json"
        self._writer.write(rich_diff, dest)
        raw = dest.read_text(encoding="utf-8")
        assert "HDX-001" in raw
        assert "HDX-002" in raw

    def test_baseline_has_seedling_header(self, tmp_path: Path, baseline_diff: FreezeDiff) -> None:
        dest = tmp_path / "diff-slack.json"
        self._writer.write(baseline_diff, dest)
        raw = dest.read_text(encoding="utf-8")
        assert "seedling" in raw
        assert "Baseline" in raw
