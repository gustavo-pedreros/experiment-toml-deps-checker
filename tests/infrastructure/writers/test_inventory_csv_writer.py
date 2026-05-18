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
    assert rows[0] == ["alias", "coordinate", "version"]


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
    assert rows == [["alias", "coordinate", "version"]]


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
    assert rows[1] == ["weird", "com.example,with-comma:art,name", "1.0.0"]


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
