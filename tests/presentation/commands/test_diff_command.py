"""Unit tests for DiffCommand."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

from gradle_deps_monitor.application.compute_freeze_diff import ComputeFreezeDiff
from gradle_deps_monitor.application.ports.snapshot_loader import (
    FindingSnapshot,
    FreezeSnapshot,
    LibrarySnapshot,
    PluginSnapshot,
)
from gradle_deps_monitor.domain.diff import FreezeDiff
from gradle_deps_monitor.presentation.commands.diff_command import DiffCommand

_TS = datetime(2026, 5, 4, 10, 0, 0, tzinfo=UTC)
_TS2 = datetime(2026, 4, 18, 10, 0, 0, tzinfo=UTC)


def _snapshot(ts: datetime = _TS) -> FreezeSnapshot:
    return FreezeSnapshot(
        schema_version="1",
        generated_at=ts,
        source_path="freeze.json",
        libraries=(LibrarySnapshot(alias="core", coordinate="com.example:core", version="1.0.0"),),
        plugins=(
            PluginSnapshot(
                alias="kotlin", plugin_id="org.jetbrains.kotlin.android", version="2.0.0"
            ),
        ),
        findings=(FindingSnapshot(rule_id="HDX-001", severity="warning", message="test"),),
    )


def _empty_diff(before_ts: datetime | None = _TS2, after_ts: datetime = _TS) -> FreezeDiff:
    return FreezeDiff(
        before_generated_at=before_ts,
        after_generated_at=after_ts,
        library_changes=(),
        plugin_changes=(),
        finding_changes=(),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_command(
    writers: list[tuple[str, MagicMock]] | None = None,
) -> tuple[DiffCommand, MagicMock, MagicMock]:
    """Return (command, mock_loader, mock_use_case)."""
    mock_loader = MagicMock()
    mock_use_case = MagicMock(spec=ComputeFreezeDiff)
    mock_use_case.execute.return_value = _empty_diff()
    if writers is None:
        writers = []
    cmd = DiffCommand(use_case=mock_use_case, loader=mock_loader, writers=writers)
    return cmd, mock_loader, mock_use_case


# ===========================================================================
# Snapshot loading
# ===========================================================================


class TestDiffCommandLoading:
    def test_loads_after_snapshot(self, tmp_path: Path) -> None:
        cmd, loader, _ = _make_command()
        after = tmp_path / "after.json"
        after.touch()
        loader.load.return_value = _snapshot()

        cmd.run(after, None, tmp_path / "out")

        loader.load.assert_called_once_with(after)

    def test_loads_both_snapshots_when_before_provided(self, tmp_path: Path) -> None:
        cmd, loader, _ = _make_command()
        after = tmp_path / "after.json"
        before = tmp_path / "before.json"
        after.touch()
        before.touch()
        loader.load.return_value = _snapshot()

        cmd.run(after, before, tmp_path / "out")

        assert loader.load.call_count == 2
        loader.load.assert_any_call(after)
        loader.load.assert_any_call(before)

    def test_passes_none_before_to_use_case_when_no_prev(self, tmp_path: Path) -> None:
        cmd, loader, use_case = _make_command()
        snap = _snapshot()
        loader.load.return_value = snap

        cmd.run(tmp_path / "a.json", None, tmp_path / "out")

        use_case.execute.assert_called_once_with(None, snap)

    def test_passes_both_snapshots_to_use_case(self, tmp_path: Path) -> None:
        cmd, loader, use_case = _make_command()
        after_snap = _snapshot(_TS)
        before_snap = _snapshot(_TS2)
        loader.load.side_effect = [after_snap, before_snap]

        cmd.run(tmp_path / "a.json", tmp_path / "b.json", tmp_path / "out")

        use_case.execute.assert_called_once_with(before_snap, after_snap)


# ===========================================================================
# Writers
# ===========================================================================


class TestDiffCommandWriters:
    def test_calls_each_writer(self, tmp_path: Path) -> None:
        w1 = MagicMock()
        w2 = MagicMock()
        cmd, loader, use_case = _make_command(writers=[("a.md", w1), ("b.json", w2)])
        diff = _empty_diff()
        use_case.execute.return_value = diff
        loader.load.return_value = _snapshot()

        out = tmp_path / "out"
        cmd.run(tmp_path / "a.json", None, out)

        w1.write.assert_called_once_with(diff, out / "a.md")
        w2.write.assert_called_once_with(diff, out / "b.json")

    def test_returns_written_paths(self, tmp_path: Path) -> None:
        w1 = MagicMock()
        w2 = MagicMock()
        cmd, loader, _ = _make_command(writers=[("diff.md", w1), ("diff.json", w2)])
        loader.load.return_value = _snapshot()

        out = tmp_path / "out"
        _, written = cmd.run(tmp_path / "x.json", None, out)

        assert written == (out / "diff.md", out / "diff.json")

    def test_no_writers_returns_empty_tuple(self, tmp_path: Path) -> None:
        cmd, loader, _ = _make_command(writers=[])
        loader.load.return_value = _snapshot()

        _, written = cmd.run(tmp_path / "x.json", None, tmp_path / "out")

        assert written == ()

    def test_returns_diff_from_use_case(self, tmp_path: Path) -> None:
        cmd, loader, use_case = _make_command()
        diff = _empty_diff()
        use_case.execute.return_value = diff
        loader.load.return_value = _snapshot()

        result_diff, _ = cmd.run(tmp_path / "x.json", None, tmp_path / "out")

        assert result_diff is diff

    def test_writer_receives_output_dir_subpath(self, tmp_path: Path) -> None:
        w = MagicMock()
        cmd, loader, _ = _make_command(writers=[("freeze-diff.md", w)])
        loader.load.return_value = _snapshot()

        out_dir = tmp_path / "reports"
        cmd.run(tmp_path / "x.json", None, out_dir)

        expected = out_dir / "freeze-diff.md"
        w.write.assert_called_once()
        _, dest = w.write.call_args.args
        assert dest == expected
