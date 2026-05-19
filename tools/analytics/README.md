# tools/analytics

Downstream analytical tooling for `gradle-deps-monitor` freeze reports.
This folder lives **outside** `src/gradle_deps_monitor/` on purpose —
it consumes the tool's CSV outputs (`freeze-inventory.csv` +
`freeze-findings.csv` from RFC-0017) rather than being part of the
shipped package. See [ADR-0010](../../docs/adr/0010-analytics-stack-duckdb.md).

## What's here

- **`schema.sql`** — typed DuckDB `CREATE TABLE` statements that mirror
  the RFC-0017 CSV contract. Single source of truth for column types
  and order.
- **`runner.py`** — CLI that loads the two CSVs, verifies their
  headers against the schema (fail-fast on drift), runs every
  `queries/*.sql` in numeric order, and emits a Markdown summary to
  stdout.
- **`render.py`** — Markdown rendering via `tabulate` over
  `rel.fetchall()`. The only allowed presentation library. Compute
  happens in SQL; this file just formats. See ADR-0010.
- **`queries/`** — the canonical query library. Read `queries/INDEX.md`
  for what counts as canonical and how to add a new query.

## Install

The analytics deps (DuckDB + tabulate) are opt-in:

```bash
pip install -e ".[analytics]"
```

Users who only run `gradle-deps-monitor check` don't pay this cost.

## Run

```bash
python tools/analytics/runner.py --dir <freeze-report-dir>
```

Where `<freeze-report-dir>` contains the two CSVs produced by
`gradle-deps-monitor check`. Example, against the bundled Sunflower
freeze:

```bash
python tools/analytics/runner.py --dir reports/sunflower-2026-05-19/
```

## Run via Claude Code

The skill `/analyze-freeze` wraps this runner. From Claude Code:

```
/analyze-freeze reports/sunflower-2026-05-19/
```

See `.claude/skills/analyze-freeze/SKILL.md` for the skill spec and
[RFC-0033](../../docs/proposals/0033-analyze-freeze-skill.md) for the
design.

## Discipline (ADR-0010)

- **Compute lives in SQL.** Filtering, joining, grouping, aggregating,
  pivoting — all in `queries/*.sql`. The `.sql` files are the asset
  that survives a port to DuckDB-WASM (planned for the RFC-0010 HTML
  export).
- **`tabulate` is the only presentation library.** The single
  touchpoint is `render.py`, which reads `rel.columns` and
  `rel.fetchall()` from a DuckDB relation and formats them as a
  GitHub-flavoured Markdown table. No pandas, no polars. If a
  future change requires dataframe-style logic here, reopen
  ADR-0010 rather than smuggling pandas back in.
- **DuckDB version is pinned** in `pyproject.toml`
  (`duckdb>=1.1,<2.0`). Re-evaluate annually; a major DuckDB upgrade
  may change `PIVOT` / window-function semantics.

## When the CSV contract changes

`runner.py` checks the header rows of both CSVs against
`_EXPECTED_INVENTORY_HEADER` and `_EXPECTED_FINDINGS_HEADER` at load
time. On mismatch it fails fast with a pointer to RFC-0017 and this
folder.

If RFC-0017 (or a successor) adds, removes, or reorders columns:

1. Update `schema.sql` first (column order matters; it's the contract).
2. Update `_EXPECTED_*_HEADER` constants in `runner.py` to match.
3. Update any affected queries in `queries/*.sql`.
4. Smoke-test against the canonical corpus
   (`reports/sunflower-2026-05-19/` for now).
