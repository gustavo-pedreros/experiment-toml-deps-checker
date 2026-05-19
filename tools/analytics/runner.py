"""CLI runner for the canonical analytics query library.

Usage:
    python tools/analytics/runner.py --dir <freeze-report-dir>

Loads ``freeze-inventory.csv`` and ``freeze-findings.csv`` from
``<freeze-report-dir>`` into in-memory DuckDB tables (per
``schema.sql``), executes every ``queries/*.sql`` in numeric order, and
emits a single Markdown document to stdout — one ``## <Title>``
section per query.

Architecture: this is downstream tooling that consumes RFC-0017 CSVs.
It lives outside ``src/gradle_deps_monitor/`` (see ADR-0010) and is
unconstrained by the project's import-linter contracts. It depends on
the optional ``[analytics]`` extra; users who install only the default
dependency set will not have ``duckdb`` available.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import duckdb

# Resolve paths relative to this file so the runner works regardless
# of the caller's working directory.
_HERE = Path(__file__).resolve().parent
_SCHEMA_PATH = _HERE / "schema.sql"
_QUERIES_DIR = _HERE / "queries"

# Expected header rows for the two CSVs. MUST match RFC-0017 exactly
# and schema.sql's column declarations. If the upstream contract
# changes, update schema.sql first, then this list.
_EXPECTED_INVENTORY_HEADER: tuple[str, ...] = (
    "alias",
    "coordinate",
    "version",
    "stability_tier",
    "latest_stable",
    "drift",
    "risk_score",
    "risk_level",
    "usage_count",
    "vulnerability_count",
    "compliance_issues",
    "license_tier",
    "health_status",
    "bom_parent",
    "duplicate_of",
)
_EXPECTED_FINDINGS_HEADER: tuple[str, ...] = (
    "section",
    "rule_id",
    "severity",
    "common_severity",
    "target",
    "message",
    "recommendation",
)


def _read_header(csv_path: Path) -> tuple[str, ...]:
    """Return the first row of *csv_path* as a tuple of strings."""
    with csv_path.open("r", newline="", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        try:
            return tuple(next(reader))
        except StopIteration:
            return ()


def _verify_header(
    csv_path: Path,
    expected: tuple[str, ...],
    label: str,
) -> None:
    """Fail fast if *csv_path*'s header doesn't match *expected*."""
    actual = _read_header(csv_path)
    if actual != expected:
        msg = (
            f"\n  {label} CSV header drift detected.\n"
            f"    file:     {csv_path}\n"
            f"    expected: {list(expected)}\n"
            f"    actual:   {list(actual)}\n"
            "  The CSV contract changed — update tools/analytics/schema.sql\n"
            "  and tools/analytics/runner.py to match. See RFC-0017 for the\n"
            "  authoritative column list.\n"
        )
        raise SystemExit(msg)


def _load_csvs(conn: duckdb.DuckDBPyConnection, report_dir: Path) -> None:
    """Apply schema.sql and INSERT the CSV contents into the typed tables."""
    schema_sql = _SCHEMA_PATH.read_text(encoding="utf-8")
    conn.execute(schema_sql)
    inventory_csv = report_dir / "freeze-inventory.csv"
    findings_csv = report_dir / "freeze-findings.csv"
    # read_csv_auto with header=True respects schema.sql column order
    # but lets DuckDB infer NULLs from empty cells (RFC-0017 semantics).
    conn.execute(
        "INSERT INTO inventory SELECT * FROM read_csv_auto(?, header=True, all_varchar=False)",
        [str(inventory_csv)],
    )
    conn.execute(
        "INSERT INTO findings SELECT * FROM read_csv_auto(?, header=True, all_varchar=True)",
        [str(findings_csv)],
    )


def _query_name(sql_path: Path) -> str:
    """Strip the leading ``NN_`` and the ``.sql`` suffix from a query filename."""
    stem = sql_path.stem
    parts = stem.split("_", 1)
    return parts[1] if len(parts) == 2 and parts[0].isdigit() else stem


# Map opt-in column → query names that depend on it. When the column
# is uniformly NULL across the inventory, the runner tells the render
# layer to emit a "Scanner not run" hint instead of a plain "no rows"
# footer for the affected queries.
_QUERIES_BY_SCANNER_COLUMN: dict[str, tuple[str, ...]] = {
    "risk_score": ("top_risk", "drift_by_severity"),
    "vulnerability_count": ("compound_security_duplicates",),
}


def _scanner_columns_all_null(conn: duckdb.DuckDBPyConnection) -> set[str]:
    """Return the set of opt-in columns that are NULL for every inventory row."""
    all_null: set[str] = set()
    for column in _QUERIES_BY_SCANNER_COLUMN:
        (count_non_null,) = conn.execute(
            f"SELECT COUNT(*) FROM inventory WHERE {column} IS NOT NULL"
        ).fetchone()
        if count_non_null == 0:
            all_null.add(column)
    return all_null


def _run_queries(conn: duckdb.DuckDBPyConnection, report_dir: Path) -> str:
    """Iterate queries/*.sql in numeric order and return the combined Markdown."""
    # Sibling import — sys.path[0] is the script directory when invoked
    # as `python tools/analytics/runner.py`. Imported lazily so a
    # missing tabulate (extra not installed) only surfaces when the
    # runner is actually invoked, not at --help time.
    import render  # type: ignore[import-not-found]

    scanner_columns_all_null = _scanner_columns_all_null(conn)
    queries_with_dead_scanner: set[str] = {
        query_name
        for column, query_names in _QUERIES_BY_SCANNER_COLUMN.items()
        if column in scanner_columns_all_null
        for query_name in query_names
    }

    sections: list[str] = []
    sql_files = sorted(_QUERIES_DIR.glob("*.sql"))
    for sql_path in sql_files:
        sql_text = sql_path.read_text(encoding="utf-8")
        rel = conn.sql(sql_text)
        name = _query_name(sql_path)
        sections.append(
            render.render_section(
                name,
                rel,
                scanner_columns_all_null=(name in queries_with_dead_scanner),
            )
        )
    return render.render_document(sections, str(report_dir))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="tools/analytics/runner.py",
        description=(
            "Run canonical DuckDB queries against a gradle-deps-monitor "
            "freeze report directory and emit a Markdown insight summary."
        ),
    )
    parser.add_argument(
        "--dir",
        required=True,
        type=Path,
        help="Freeze report directory containing freeze-inventory.csv and freeze-findings.csv.",
    )
    args = parser.parse_args(argv)

    report_dir: Path = args.dir.resolve()
    inventory_csv = report_dir / "freeze-inventory.csv"
    findings_csv = report_dir / "freeze-findings.csv"
    for csv_path, label in [
        (inventory_csv, "freeze-inventory.csv"),
        (findings_csv, "freeze-findings.csv"),
    ]:
        if not csv_path.is_file():
            sys.stderr.write(
                f"error: {label} not found in {report_dir}.\n"
                "  This file is produced by `gradle-deps-monitor check` "
                "(RFC-0017, v0.1.0+).\n"
            )
            return 2

    _verify_header(inventory_csv, _EXPECTED_INVENTORY_HEADER, "inventory")
    _verify_header(findings_csv, _EXPECTED_FINDINGS_HEADER, "findings")

    conn = duckdb.connect(database=":memory:")
    try:
        _load_csvs(conn, report_dir)
        document = _run_queries(conn, report_dir)
    finally:
        conn.close()

    sys.stdout.write(document)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
