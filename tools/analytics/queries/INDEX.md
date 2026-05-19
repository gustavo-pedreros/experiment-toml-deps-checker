# Canonical Query Library

This folder is the **canonical question set** for analysing a
`gradle-deps-monitor` freeze report. Each `NN_<name>.sql` file is a
self-contained DuckDB query against the two RFC-0017 tables
(`inventory`, `findings`) declared in `../schema.sql`.

The discipline is set by [ADR-0010](../../../docs/adr/0010-analytics-stack-duckdb.md):

> All compute happens in SQL. The presentation layer (`render.py`)
> uses `tabulate` only — no pandas, no polars, no client-side
> dataframe library.

If you find yourself reaching for a dataframe library to filter,
join, group, or pivot — stop. Put it in SQL. The `.sql` files are
the asset that survives the future port to DuckDB-WASM (RFC-0010
HTML export); `render.py` is throwaway in that scenario.

## When is a query "canonical"?

A query is canonical iff it satisfies **all four** of these:

1. **Generalizable** — answers a question any Android project could
   ask. Not specific to one corpus, one team, or one vendor's
   conventions. If the query only makes sense for "our fintech
   catalog" or "the Sunflower sample app", it is **not** canonical.
2. **Repeatable insight** — a reviewer asks this every freeze, not
   once. "Diff vs last freeze" is not canonical (that's
   `gradle-deps-monitor diff`); "top risk in the current freeze" is.
3. **Compresses signal** — output is shorter than the raw CSV slice
   it queries. A "show me everything" query is not canonical; the
   raw CSV already does that.
4. **Self-contained SQL** — single `SELECT` (CTEs OK) against the
   two declared tables. No DuckDB-only extensions, no `INSTALL`,
   no temp tables — anything that wouldn't survive a port to
   DuckDB-WASM blocks the query from being canonical.

Soft signals (nudge toward canonical, don't decide alone):

- Pairs naturally with an existing section in `freeze.md`.
- Touches a column that other canonical queries don't (broadens
  coverage of the 15-column inventory + 7-column findings surface).
- Answers a question the maintainers have heard twice from users.

## How to add a query

1. Validate against the 4 criteria above. If you can't tick all
   four, the query is fine as an ad-hoc lookup but doesn't belong
   in this folder.
2. Add `NN_<name>.sql` (next available number, snake_case name).
3. Open a header comment in the file that:
   - States the question the query answers in one sentence.
   - Explains why the query meets each of the 4 criteria.
   - Notes any opt-in gating (`WHERE risk_score IS NOT NULL`, etc.).
4. Add a row to the registry below.
5. If the query introduces a new column reference or enum value
   not currently in `../schema.sql`, update the schema to match.
6. Add the query's display title to `TITLES` in `../render.py`.
7. Manual run via `python tools/analytics/runner.py --dir
   reports/sunflower-2026-05-19/` confirms the new section appears.

## Registry

| # | Name | Purpose | Columns touched | What it tells a reviewer |
|---|------|---------|-----------------|--------------------------|
| 01 | `top_risk` | Top 15 libraries by composite risk score with explanatory dimensions | `alias`, `coordinate`, `version`, `risk_score`, `risk_level`, `drift`, `vulnerability_count`, `license_tier` | Where to start triage. Compresses the 5-dimension risk story into one ranked list. |

> The 7 queries planned for PR2 (`02_drift_by_severity` …
> `08_bom_coverage`) are documented in [RFC-0033](../../../docs/proposals/0033-analyze-freeze-skill.md);
> their rows land in this registry as each query is added.

## Coverage

The canonical library aims to touch every distinct CSV dimension at
least once: `risk`, `drift`, `stability`, `health`, `license`,
`usage`, `bom`, `duplicates`, and the cross-cutting `findings`
section/severity. When proposing a new query, check whether it
broadens coverage or duplicates an existing dimension.
