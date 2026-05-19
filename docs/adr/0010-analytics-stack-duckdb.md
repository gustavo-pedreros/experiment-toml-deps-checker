# ADR-0010: Analytics stack — DuckDB as the query layer for downstream insights

## Status

Accepted — 2026-05-19

## Context

The CSV exports shipped in [RFC-0017](../proposals/0017-csv-export.md)
(Phase 5) are a deliberate interchange surface: a 15-column
`freeze-inventory.csv` and a 7-column `freeze-findings.csv`, both with
explicit append-only column contracts, written atomically per
[RFC-0032](../proposals/0032-atomic-writes.md). Their stated purpose
is "a flat, machine-readable audit trail that consumers can ingest
into spreadsheets, BI tools, or future HTML views."

To date, no downstream consumer exists. The most a reviewer can do
with the CSVs today is open them in a spreadsheet and squint, or
manually correlate findings across sections (e.g. the RFC-0017
issue-#13 "duplicate alias with CVE" story still requires
hand-joining `inventory.csv` rows on `coordinate`).

Phase 8 introduces the first analytical consumer of the CSVs (a
Claude Code skill, see [RFC-0033](../proposals/0033-analyze-freeze-skill.md)),
and positions further consumers (notably [RFC-0010](../proposals/0010-html-export.md)
HTML export, currently 📋 Planned in Phase 8) downstream of the same
query layer. Before writing the first consumer, the project needs a
clear constraint on **how downstream consumers compute against the
CSVs** — otherwise the choice of query engine and rendering library
gets re-litigated per consumer, and each consumer drifts toward its
own dialect.

Several options were considered:

- **Pandas-only.** Mature, batteries-included. But pandas-as-compute
  doesn't survive a port to the browser; the planned HTML report
  (RFC-0010) would have to rewrite every transform in JavaScript.
- **Polars-only.** Faster and more ergonomic than pandas, but with
  a smaller LLM/community surface today, no mature browser story,
  and no compelling reason to bring it in for catalogs of ≤200 rows.
- **DuckDB-only.** SQL is the lingua franca of analytics; DuckDB
  reads CSVs natively (`SELECT FROM 'foo.csv'`), supports joins
  across files in one query, handles RFC-0017's empty-cell semantics
  via CSV NULL inference, and — critically — ships as DuckDB-WASM
  for browser-time consumption. Same SQL files run unchanged in
  Python and in the browser.
- **DuckDB for compute, pandas for render only.** A hybrid where
  the `.sql` files are the portable asset and pandas is confined
  to a single render function that calls `to_markdown()`. Keeps
  the compute layer browser-portable; gains a one-line Markdown
  emitter without re-implementing tabulation.

The CSV contract itself is implicit (no `schema_version` field —
[RFC-0017](../proposals/0017-csv-export.md) declined to add one to
the CSVs even though `freeze.json` has one per ADR-0008). Any query
layer therefore needs a fail-fast header check at load time to
detect upstream column drift.

## Decision

**DuckDB is the SQL engine for all downstream analytics.** Queries
live as portable `.sql` files in `tools/analytics/queries/`, one
file per canonical question. Each file is self-contained: a single
`SELECT` (CTEs OK) against the two declared tables `inventory` and
`findings`, with no DuckDB-only extensions that won't survive a
port to DuckDB-WASM.

**Pandas is permitted only in the render layer** (`tools/analytics/render.py`).
The single allowed pandas touchpoint is `DuckDBPyRelation.df()` →
`DataFrame.to_markdown()`. Computation — filtering, joining, grouping,
aggregating, pivoting — happens in SQL. This is a discipline-based
rule, not a tooling-enforced one; reviewers check it at PR time.

**Analytics code lives outside the shipped package.** `tools/analytics/`
is a sibling of `src/`, intentionally outside `src/gradle_deps_monitor/`
and the 6 Clean Architecture layers from [ADR-0006](0006-pragmatic-clean-architecture.md).
The `import-linter` contracts in `pyproject.toml` only cover
`gradle_deps_monitor.*`, so the analytics layer is unconstrained by
them — and the main install path is unburdened by data-science
dependencies.

**Dependencies are opt-in** via a new `[project.optional-dependencies]
analytics` extra:

```toml
analytics = ["duckdb>=1.1,<2.0", "pandas>=2.2", "tabulate>=0.9"]
```

Install: `pip install -e ".[analytics]"`. Users who only run
`gradle-deps-monitor check` never pay the cost. `tabulate` is pinned
explicitly because pandas 3.x dropped it as a transitive dependency;
`DataFrame.to_markdown()` still requires it at call time.

**The CSV contract is enforced at load time.** `tools/analytics/runner.py`
reads the header row of each CSV, compares it against the expected
column list (mirrored in `tools/analytics/schema.sql`), and fails
fast with a pointer to RFC-0017 + `schema.sql` on mismatch. This is
the implicit-versioning mechanism the CSVs lack.

## Consequences

**Positive**

- **Zero new runtime deps for the shipped package.** Default
  `pip install gradle-deps-monitor` is unchanged. Only `pip install
  -e ".[analytics]"` pulls DuckDB + pandas.
- **Queries survive a future migration to DuckDB-WASM.** The day
  RFC-0010 (HTML export) ships, `runner.py` and `render.py` are
  replaced by JavaScript loaders and renderers; the `.sql` files
  in `queries/` don't change. The portability is the asset.
- **SQL is reviewable by non-Python contributors.** Database
  engineers, data analysts, and JS developers can read and propose
  new canonical queries without learning the Python API surface
  of pandas or polars.
- **RFC-0017's empty-cell semantics work natively.** Empty cells
  in CSVs (meaning "scanner not run") are inferred as `NULL` by
  DuckDB; queries that depend on opt-in scanners gate with
  `IS NOT NULL` and the render layer detects all-NULL columns to
  emit "Scanner not run" hints.
- **Architecture boundaries stay clean.** `tools/analytics/`
  outside `src/` means no new import-linter contract is needed, no
  Clean Architecture layer is introduced, and the dependency
  direction is enforced by physical location.

**Negative**

- **Three deps in `[analytics]` instead of one.** Accepted in
  exchange for `pandas.DataFrame.to_markdown()` ergonomics; the
  alternative (`tabulate`-only render) requires hand-rolling column
  alignment and would still pull a render dep. `tabulate` is the
  only user-facing import beyond DuckDB and pandas — and only
  because pandas 3.x dropped the transitive pull that made the
  call self-sufficient in pandas 2.x.
- **"SQL for compute, pandas for render" is a discipline-based
  rule, not tooling-enforced.** No linter prevents a future
  contributor from sneaking compute into `render.py`. Mitigated
  by: (a) the rule restated in `tools/analytics/README.md` and
  `tools/analytics/queries/INDEX.md`; (b) the single `df = rel.df()`
  touchpoint making any new `df.<method>()` call beyond `to_markdown()`
  visible at code review.
- **DuckDB version drift is a new operational concern.** A query
  that works on DuckDB 1.1 might behave differently on 1.3 or 2.0
  (e.g. `PIVOT` syntax changes). Mitigated by the pinned range
  `duckdb>=1.1,<2.0` in `pyproject.toml`; re-evaluate on every
  DuckDB major.
- **Implicit CSV contract enforcement.** Header-check in `runner.py`
  is the only safeguard against upstream column drift. If RFC-0017
  ever needs a true `schema_version`, the check is the migration
  point.

## Related

- [ADR-0006](0006-pragmatic-clean-architecture.md) — Pragmatic
  Clean Architecture. The analytics layer lives **outside** the
  six layers ADR-0006 defines; ADR-0010 explicitly carves it out
  as downstream tooling rather than a new layer.
- [ADR-0008](0008-json-schema-semver.md) — JSON `schema_version`
  semantics. The CSVs deliberately do not have a `schema_version`
  field; ADR-0010's header-check is the substitute.
- [ADR-0009](0009-tracer-bullets-and-spikes.md) — Tracer Bullets.
  The first consumer (RFC-0033) follows the tracer pattern: one
  end-to-end query in PR1, the remaining canonical library in PR2.
- [RFC-0017](../proposals/0017-csv-export.md) — the CSV contract
  this ADR builds on top of.
- [RFC-0033](../proposals/0033-analyze-freeze-skill.md) — first
  consumer of this stack: the `/analyze-freeze` Claude Code skill.
- [RFC-0010](../proposals/0010-html-export.md) — planned second
  consumer (HTML export), expected to reuse the same `.sql` query
  library via DuckDB-WASM.
