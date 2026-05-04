"""Unit tests for ComputeFreezeDiff use case."""

from __future__ import annotations

from datetime import UTC, datetime

from gradle_deps_monitor.application.compute_freeze_diff import ComputeFreezeDiff
from gradle_deps_monitor.application.ports.snapshot_loader import (
    FindingSnapshot,
    FreezeSnapshot,
    LibrarySnapshot,
    PluginSnapshot,
)
from gradle_deps_monitor.domain.diff import VersionBump

_BEFORE_TS = datetime(2026, 4, 18, 10, 0, 0, tzinfo=UTC)
_AFTER_TS = datetime(2026, 5, 4, 10, 0, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _snapshot(
    *,
    ts: datetime,
    libraries: tuple[LibrarySnapshot, ...] = (),
    plugins: tuple[PluginSnapshot, ...] = (),
    findings: tuple[FindingSnapshot, ...] = (),
) -> FreezeSnapshot:
    return FreezeSnapshot(
        schema_version="1",
        generated_at=ts,
        source_path="gradle/libs.versions.toml",
        libraries=libraries,
        plugins=plugins,
        findings=findings,
    )


def _lib(alias: str, version: str) -> LibrarySnapshot:
    return LibrarySnapshot(alias=alias, coordinate=f"com.example:{alias}", version=version)


def _plugin(alias: str, version: str) -> PluginSnapshot:
    return PluginSnapshot(alias=alias, plugin_id=f"org.example.{alias}", version=version)


def _finding(rule_id: str, message: str = "msg") -> FindingSnapshot:
    return FindingSnapshot(rule_id=rule_id, severity="warning", message=message)


_USE_CASE = ComputeFreezeDiff()


# ---------------------------------------------------------------------------
# Baseline (before=None)
# ---------------------------------------------------------------------------


def test_baseline_when_no_before() -> None:
    after = _snapshot(ts=_AFTER_TS, libraries=(_lib("core-ktx", "1.13.0"),))
    diff = _USE_CASE.execute(before=None, after=after)

    assert diff.is_baseline is True
    assert diff.before_generated_at is None
    assert diff.after_generated_at == _AFTER_TS
    assert diff.library_changes == ()


# ---------------------------------------------------------------------------
# Timestamps
# ---------------------------------------------------------------------------


def test_timestamps_preserved() -> None:
    before = _snapshot(ts=_BEFORE_TS)
    after = _snapshot(ts=_AFTER_TS)
    diff = _USE_CASE.execute(before, after)

    assert diff.before_generated_at == _BEFORE_TS
    assert diff.after_generated_at == _AFTER_TS


# ---------------------------------------------------------------------------
# Library diffs
# ---------------------------------------------------------------------------


def test_library_added() -> None:
    before = _snapshot(ts=_BEFORE_TS)
    after = _snapshot(ts=_AFTER_TS, libraries=(_lib("core-ktx", "1.13.0"),))
    diff = _USE_CASE.execute(before, after)

    assert len(diff.libraries_added) == 1
    change = diff.libraries_added[0]
    assert change.alias == "core-ktx"
    assert change.coordinate == "com.example:core-ktx"
    assert change.before_version is None
    assert change.after_version == "1.13.0"
    assert change.bump is None


def test_library_removed() -> None:
    before = _snapshot(ts=_BEFORE_TS, libraries=(_lib("core-ktx", "1.13.0"),))
    after = _snapshot(ts=_AFTER_TS)
    diff = _USE_CASE.execute(before, after)

    assert len(diff.libraries_removed) == 1
    change = diff.libraries_removed[0]
    assert change.alias == "core-ktx"
    assert change.before_version == "1.13.0"
    assert change.after_version is None


def test_library_unchanged_not_in_diff() -> None:
    lib = _lib("core-ktx", "1.13.0")
    before = _snapshot(ts=_BEFORE_TS, libraries=(lib,))
    after = _snapshot(ts=_AFTER_TS, libraries=(lib,))
    diff = _USE_CASE.execute(before, after)

    assert diff.library_changes == ()


def test_library_major_upgrade() -> None:
    before = _snapshot(ts=_BEFORE_TS, libraries=(_lib("core-ktx", "1.13.0"),))
    after = _snapshot(ts=_AFTER_TS, libraries=(_lib("core-ktx", "2.0.0"),))
    diff = _USE_CASE.execute(before, after)

    assert len(diff.libraries_major) == 1
    assert diff.library_changes[0].bump == VersionBump.MAJOR


def test_library_minor_upgrade() -> None:
    before = _snapshot(ts=_BEFORE_TS, libraries=(_lib("core-ktx", "1.12.0"),))
    after = _snapshot(ts=_AFTER_TS, libraries=(_lib("core-ktx", "1.13.0"),))
    diff = _USE_CASE.execute(before, after)

    assert len(diff.libraries_minor) == 1


def test_library_patch_upgrade() -> None:
    before = _snapshot(ts=_BEFORE_TS, libraries=(_lib("core-ktx", "1.13.0"),))
    after = _snapshot(ts=_AFTER_TS, libraries=(_lib("core-ktx", "1.13.1"),))
    diff = _USE_CASE.execute(before, after)

    assert len(diff.libraries_patch) == 1


def test_library_downgrade() -> None:
    before = _snapshot(ts=_BEFORE_TS, libraries=(_lib("core-ktx", "2.0.0"),))
    after = _snapshot(ts=_AFTER_TS, libraries=(_lib("core-ktx", "1.13.0"),))
    diff = _USE_CASE.execute(before, after)

    assert len(diff.libraries_downgraded) == 1


def test_multiple_libraries_mixed_changes() -> None:
    before = _snapshot(
        ts=_BEFORE_TS,
        libraries=(
            _lib("core-ktx", "1.12.0"),
            _lib("appcompat", "1.6.0"),
            _lib("old-lib", "1.0.0"),
        ),
    )
    after = _snapshot(
        ts=_AFTER_TS,
        libraries=(
            _lib("core-ktx", "1.13.0"),  # minor upgrade
            _lib("appcompat", "1.6.0"),  # unchanged
            _lib("new-lib", "1.0.0"),  # added
        ),
    )
    diff = _USE_CASE.execute(before, after)

    assert len(diff.library_changes) == 3  # minor + removed + added
    assert len(diff.libraries_upgraded) == 1
    assert len(diff.libraries_added) == 1
    assert len(diff.libraries_removed) == 1


# ---------------------------------------------------------------------------
# Plugin diffs
# ---------------------------------------------------------------------------


def test_plugin_added() -> None:
    before = _snapshot(ts=_BEFORE_TS)
    after = _snapshot(ts=_AFTER_TS, plugins=(_plugin("kotlin-android", "2.0.0"),))
    diff = _USE_CASE.execute(before, after)

    assert len(diff.plugins_added) == 1
    assert diff.plugins_added[0].alias == "kotlin-android"


def test_plugin_removed() -> None:
    before = _snapshot(ts=_BEFORE_TS, plugins=(_plugin("kotlin-android", "2.0.0"),))
    after = _snapshot(ts=_AFTER_TS)
    diff = _USE_CASE.execute(before, after)

    assert len(diff.plugins_removed) == 1


def test_plugin_unchanged_not_in_diff() -> None:
    p = _plugin("kotlin-android", "2.0.0")
    before = _snapshot(ts=_BEFORE_TS, plugins=(p,))
    after = _snapshot(ts=_AFTER_TS, plugins=(p,))
    diff = _USE_CASE.execute(before, after)

    assert diff.plugin_changes == ()


def test_plugin_upgraded() -> None:
    before = _snapshot(ts=_BEFORE_TS, plugins=(_plugin("kotlin-android", "1.9.0"),))
    after = _snapshot(ts=_AFTER_TS, plugins=(_plugin("kotlin-android", "2.0.0"),))
    diff = _USE_CASE.execute(before, after)

    assert len(diff.plugins_upgraded) == 1
    assert diff.plugin_changes[0].bump == VersionBump.MAJOR


# ---------------------------------------------------------------------------
# Finding diffs
# ---------------------------------------------------------------------------


def test_finding_introduced() -> None:
    before = _snapshot(ts=_BEFORE_TS)
    after = _snapshot(ts=_AFTER_TS, findings=(_finding("HDX-001"),))
    diff = _USE_CASE.execute(before, after)

    assert len(diff.findings_introduced) == 1
    assert diff.findings_introduced[0].rule_id == "HDX-001"
    assert diff.findings_introduced[0].status == "introduced"


def test_finding_resolved() -> None:
    before = _snapshot(ts=_BEFORE_TS, findings=(_finding("HDX-001"),))
    after = _snapshot(ts=_AFTER_TS)
    diff = _USE_CASE.execute(before, after)

    assert len(diff.findings_resolved) == 1
    assert diff.findings_resolved[0].status == "resolved"


def test_finding_unchanged_not_in_diff() -> None:
    f = _finding("HDX-001")
    before = _snapshot(ts=_BEFORE_TS, findings=(f,))
    after = _snapshot(ts=_AFTER_TS, findings=(f,))
    diff = _USE_CASE.execute(before, after)

    assert diff.finding_changes == ()


def test_finding_introduced_and_resolved_simultaneously() -> None:
    before = _snapshot(ts=_BEFORE_TS, findings=(_finding("HDX-002"),))
    after = _snapshot(ts=_AFTER_TS, findings=(_finding("HDX-001"),))
    diff = _USE_CASE.execute(before, after)

    assert len(diff.findings_introduced) == 1
    assert len(diff.findings_resolved) == 1


# ---------------------------------------------------------------------------
# has_changes
# ---------------------------------------------------------------------------


def test_has_changes_false_when_identical() -> None:
    libs = (_lib("core-ktx", "1.13.0"),)
    before = _snapshot(ts=_BEFORE_TS, libraries=libs)
    after = _snapshot(ts=_AFTER_TS, libraries=libs)
    diff = _USE_CASE.execute(before, after)

    assert diff.has_changes is False


def test_has_changes_true_when_library_added() -> None:
    before = _snapshot(ts=_BEFORE_TS)
    after = _snapshot(ts=_AFTER_TS, libraries=(_lib("new-lib", "1.0.0"),))
    diff = _USE_CASE.execute(before, after)

    assert diff.has_changes is True
