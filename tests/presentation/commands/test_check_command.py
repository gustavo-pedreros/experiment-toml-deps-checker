"""Unit tests for CheckCommand."""

from __future__ import annotations

from pathlib import Path

import pytest

from gradle_deps_monitor.domain import FreezeReport
from gradle_deps_monitor.domain.catalog import Catalog
from gradle_deps_monitor.presentation.commands.check_command import CheckCommand

# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------

_FAKE_CATALOG_PATH = Path("/fake/gradle")


class _FixedUseCase:
    """Stub use case that always returns a fixed report."""

    def __init__(self, report: FreezeReport) -> None:
        self._report = report
        self.received_path: Path | None = None

    def execute(self, catalog_path: Path) -> FreezeReport:
        self.received_path = catalog_path
        return self._report


class _CapturingWriter:
    """Stub writer that records every call."""

    def __init__(self) -> None:
        self.calls: list[tuple[FreezeReport, Path]] = []

    def write(self, report: FreezeReport, dest: Path) -> None:
        self.calls.append((report, dest))


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def empty_report(tmp_path: Path) -> FreezeReport:
    catalog = Catalog(
        source_path=tmp_path / "libs.versions.toml",
        libraries=(),
        plugins=(),
        bundles=(),
    )
    return FreezeReport(catalog=catalog)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_run_returns_report(empty_report: FreezeReport, tmp_path: Path) -> None:
    cmd = CheckCommand(use_case=_FixedUseCase(empty_report), writers=[])
    report, _ = cmd.run(_FAKE_CATALOG_PATH, tmp_path / "out")
    assert report is empty_report


def test_run_returns_written_file_paths(empty_report: FreezeReport, tmp_path: Path) -> None:
    out = tmp_path / "reports"
    cmd = CheckCommand(
        use_case=_FixedUseCase(empty_report),
        writers=[("freeze.md", _CapturingWriter()), ("freeze.json", _CapturingWriter())],
    )
    _, written = cmd.run(_FAKE_CATALOG_PATH, out)
    assert written == (out / "freeze.md", out / "freeze.json")


def test_run_forwards_catalog_path_to_use_case(empty_report: FreezeReport, tmp_path: Path) -> None:
    use_case = _FixedUseCase(empty_report)
    cmd = CheckCommand(use_case=use_case, writers=[])
    cmd.run(_FAKE_CATALOG_PATH, tmp_path / "out")
    assert use_case.received_path == _FAKE_CATALOG_PATH


def test_run_calls_each_writer_once(empty_report: FreezeReport, tmp_path: Path) -> None:
    md = _CapturingWriter()
    json = _CapturingWriter()
    cmd = CheckCommand(
        use_case=_FixedUseCase(empty_report),
        writers=[("freeze.md", md), ("freeze.json", json)],
    )
    cmd.run(_FAKE_CATALOG_PATH, tmp_path / "out")
    assert len(md.calls) == 1
    assert len(json.calls) == 1


def test_run_passes_correct_dest_to_writers(empty_report: FreezeReport, tmp_path: Path) -> None:
    md = _CapturingWriter()
    json = _CapturingWriter()
    out = tmp_path / "reports"
    cmd = CheckCommand(
        use_case=_FixedUseCase(empty_report),
        writers=[("freeze.md", md), ("freeze.json", json)],
    )
    cmd.run(_FAKE_CATALOG_PATH, out)
    assert md.calls[0][1] == out / "freeze.md"
    assert json.calls[0][1] == out / "freeze.json"


def test_run_passes_report_to_writers(empty_report: FreezeReport, tmp_path: Path) -> None:
    writer = _CapturingWriter()
    cmd = CheckCommand(
        use_case=_FixedUseCase(empty_report),
        writers=[("freeze.md", writer)],
    )
    cmd.run(_FAKE_CATALOG_PATH, tmp_path / "out")
    assert writer.calls[0][0] is empty_report


def test_run_with_no_writers_succeeds(empty_report: FreezeReport, tmp_path: Path) -> None:
    cmd = CheckCommand(use_case=_FixedUseCase(empty_report), writers=[])
    report, written = cmd.run(_FAKE_CATALOG_PATH, tmp_path / "out")
    assert report is empty_report
    assert written == ()
