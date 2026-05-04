"""Unit tests for domain/diff.py — FreezeDiff, VersionBump, classify_bump."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from gradle_deps_monitor.domain.diff import (
    FindingChange,
    FreezeDiff,
    LibraryChange,
    PluginChange,
    VersionBump,
    classify_bump,
)

_NOW = datetime(2026, 5, 4, 10, 0, 0, tzinfo=UTC)
_BEFORE = datetime(2026, 4, 18, 10, 0, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# classify_bump
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("before", "after", "expected"),
    [
        ("1.12.0", "2.0.0", VersionBump.MAJOR),
        ("1.12.0", "1.13.0", VersionBump.MINOR),
        ("1.12.0", "1.12.1", VersionBump.PATCH),
        ("1.0.0-alpha01", "1.0.0-alpha02", VersionBump.PRE_RELEASE),
        ("1.0.0-alpha01", "1.0.0", VersionBump.PRE_RELEASE),
        ("2.0.0", "1.13.0", VersionBump.DOWNGRADE),
        ("1.13.0", "1.12.0", VersionBump.DOWNGRADE),
        ("1.12.1", "1.12.0", VersionBump.DOWNGRADE),
        # Non-standard versions — fall back to (0,0,0) comparison
        ("unknown", "unknown", VersionBump.PRE_RELEASE),
        ("1.0", "2.0", VersionBump.MAJOR),
        ("1", "2", VersionBump.MAJOR),
    ],
)
def test_classify_bump(before: str, after: str, expected: VersionBump) -> None:
    assert classify_bump(before, after) == expected


# ---------------------------------------------------------------------------
# LibraryChange.kind
# ---------------------------------------------------------------------------


def test_library_change_kind_added() -> None:
    c = LibraryChange(
        alias="foo",
        coordinate="com.example:foo",
        before_version=None,
        after_version="1.0.0",
        bump=None,
    )
    assert c.kind == "added"


def test_library_change_kind_removed() -> None:
    c = LibraryChange(
        alias="foo",
        coordinate="com.example:foo",
        before_version="1.0.0",
        after_version=None,
        bump=None,
    )
    assert c.kind == "removed"


def test_library_change_kind_upgraded() -> None:
    c = LibraryChange(
        alias="foo",
        coordinate="com.example:foo",
        before_version="1.0.0",
        after_version="2.0.0",
        bump=VersionBump.MAJOR,
    )
    assert c.kind == "upgraded"


def test_library_change_kind_downgraded() -> None:
    c = LibraryChange(
        alias="foo",
        coordinate="com.example:foo",
        before_version="2.0.0",
        after_version="1.0.0",
        bump=VersionBump.DOWNGRADE,
    )
    assert c.kind == "downgraded"


def test_library_change_kind_pre_release() -> None:
    c = LibraryChange(
        alias="foo",
        coordinate="com.example:foo",
        before_version="1.0.0-alpha01",
        after_version="1.0.0-alpha02",
        bump=VersionBump.PRE_RELEASE,
    )
    assert c.kind == "pre-release"


# ---------------------------------------------------------------------------
# FreezeDiff convenience properties
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
    return FindingChange(rule_id=rule_id, severity="warning", message="msg", status=status)  # type: ignore[arg-type]


@pytest.fixture()
def rich_diff() -> FreezeDiff:
    return FreezeDiff(
        before_generated_at=_BEFORE,
        after_generated_at=_NOW,
        library_changes=(
            _lib("added-lib", None, "1.0.0", None),
            _lib("removed-lib", "1.0.0", None, None),
            _lib("major-lib", "1.0.0", "2.0.0", VersionBump.MAJOR),
            _lib("minor-lib", "1.0.0", "1.1.0", VersionBump.MINOR),
            _lib("patch-lib", "1.0.0", "1.0.1", VersionBump.PATCH),
            _lib("pre-lib", "1.0.0-alpha01", "1.0.0-alpha02", VersionBump.PRE_RELEASE),
            _lib("down-lib", "2.0.0", "1.0.0", VersionBump.DOWNGRADE),
        ),
        plugin_changes=(
            _plugin("added-plugin", None, "1.0.0", None),
            _plugin("removed-plugin", "1.0.0", None, None),
            _plugin("upgraded-plugin", "1.0.0", "2.0.0", VersionBump.MAJOR),
            _plugin("downgraded-plugin", "2.0.0", "1.0.0", VersionBump.DOWNGRADE),
        ),
        finding_changes=(
            _finding("HDX-001", "introduced"),
            _finding("HDX-002", "resolved"),
        ),
    )


def test_libraries_added(rich_diff: FreezeDiff) -> None:
    result = rich_diff.libraries_added
    assert len(result) == 1
    assert result[0].alias == "added-lib"


def test_libraries_removed(rich_diff: FreezeDiff) -> None:
    result = rich_diff.libraries_removed
    assert len(result) == 1
    assert result[0].alias == "removed-lib"


def test_libraries_upgraded(rich_diff: FreezeDiff) -> None:
    # upgraded = major + minor + patch + pre-release (not downgrade, not add/remove)
    upgraded = rich_diff.libraries_upgraded
    aliases = {c.alias for c in upgraded}
    assert "major-lib" in aliases
    assert "minor-lib" in aliases
    assert "patch-lib" in aliases
    assert "pre-lib" in aliases
    assert "down-lib" not in aliases
    assert "added-lib" not in aliases
    assert "removed-lib" not in aliases


def test_libraries_downgraded(rich_diff: FreezeDiff) -> None:
    result = rich_diff.libraries_downgraded
    assert len(result) == 1
    assert result[0].alias == "down-lib"


def test_libraries_major(rich_diff: FreezeDiff) -> None:
    result = rich_diff.libraries_major
    assert len(result) == 1
    assert result[0].alias == "major-lib"


def test_libraries_minor(rich_diff: FreezeDiff) -> None:
    result = rich_diff.libraries_minor
    assert len(result) == 1
    assert result[0].alias == "minor-lib"


def test_libraries_patch(rich_diff: FreezeDiff) -> None:
    result = rich_diff.libraries_patch
    assert len(result) == 1
    assert result[0].alias == "patch-lib"


def test_plugins_added(rich_diff: FreezeDiff) -> None:
    assert len(rich_diff.plugins_added) == 1


def test_plugins_removed(rich_diff: FreezeDiff) -> None:
    assert len(rich_diff.plugins_removed) == 1


def test_plugins_upgraded(rich_diff: FreezeDiff) -> None:
    assert len(rich_diff.plugins_upgraded) == 1


def test_plugins_downgraded(rich_diff: FreezeDiff) -> None:
    assert len(rich_diff.plugins_downgraded) == 1


def test_findings_introduced(rich_diff: FreezeDiff) -> None:
    result = rich_diff.findings_introduced
    assert len(result) == 1
    assert result[0].rule_id == "HDX-001"


def test_findings_resolved(rich_diff: FreezeDiff) -> None:
    result = rich_diff.findings_resolved
    assert len(result) == 1
    assert result[0].rule_id == "HDX-002"


def test_has_changes_true(rich_diff: FreezeDiff) -> None:
    assert rich_diff.has_changes is True


def test_has_changes_false() -> None:
    empty = FreezeDiff(
        before_generated_at=_BEFORE,
        after_generated_at=_NOW,
        library_changes=(),
        plugin_changes=(),
        finding_changes=(),
    )
    assert empty.has_changes is False


# ---------------------------------------------------------------------------
# Baseline
# ---------------------------------------------------------------------------


def test_baseline_flag() -> None:
    baseline = FreezeDiff(
        before_generated_at=None,
        after_generated_at=_NOW,
        library_changes=(),
        plugin_changes=(),
        finding_changes=(),
        is_baseline=True,
    )
    assert baseline.is_baseline is True
    assert baseline.before_generated_at is None


def test_non_baseline_by_default() -> None:
    diff = FreezeDiff(
        before_generated_at=_BEFORE,
        after_generated_at=_NOW,
        library_changes=(),
        plugin_changes=(),
        finding_changes=(),
    )
    assert diff.is_baseline is False
