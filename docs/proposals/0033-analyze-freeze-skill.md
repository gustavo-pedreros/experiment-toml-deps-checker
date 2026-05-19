# RFC-0033: `/analyze-freeze` skill and canonical query library

**Status:** Implemented
**Created:** 2026-05-19
**Shipped:** 2026-05-19 (PR1 #75 tracer + PR2 fill)
**Related JTBDs:** JTBD-5 (operator control), JTBD-3 (reproducible runs)
**Depends on:** ADR-0010 (analytics stack — DuckDB), RFC-0017 (CSV export)
**Opens phase:** Phase 8 — Analytics & insights

## Problem

The CSV exports shipped in [RFC-0017](0017-csv-export.md) (Phase 5)
were designed as a "technical audit trail that consumers can ingest
into spreadsheets, BI tools, or future HTML views." Six months later,
no canonical consumer exists. A reviewer who wants more than the
narrative `freeze.md` opens `freeze-inventory.csv` in a spreadsheet
and scrolls.

Three specific pain points show up every time the tool is run against
a non-trivial catalog:

1. **Compound stories are invisible.** RFC-0017 issue-#13 (a
   duplicate alias where one copy has CVEs) is the exact reason the
   CSVs exist as a join surface — and today nobody actually joins
   them. The story requires manually correlating `coordinate`
   between two rows of `inventory.csv`.
2. **Risk triage is unsorted.** With `--risk-score`, every library
   carries a score and a level, but the only ordered view in
   `freeze.md` is "Top 10". Operators with 200-library catalogs
   want "top 15 by score with drift + CVE + license columns
   joined" — and they get to write the SQL themselves.
3. **The maintainers' standard questions go unanswered.** "How
   much of the catalog is major drift × HIGH risk?", "Which
   pre-release tiers are shipping?", "What's my license cohort?" —
   each one is a one-line SQL question against the CSVs, but
   without a place to put canonical answers they re-emerge
   ad-hoc every freeze.

There is also a deeper concern. The project has accumulated
sub-agents (`.claude/agents/housekeeper.md`, `.claude/agents/test-runner.md`)
but no skills. The first skill is itself a small but real
investment: it codifies a procedure, sets a tone for future skills,
and ties Claude Code into the project's lifecycle. Postponing the
first skill indefinitely is the same kind of debt the CSVs
themselves accumulated.

## Goals

1. **Ship `/analyze-freeze`** as the project's first Claude Code
   skill. Takes a freeze report directory, runs canonical queries
   against `freeze-inventory.csv` + `freeze-findings.csv`, emits a
   single Markdown document to stdout.
2. **Establish a canonical query library** — 8 self-contained `.sql`
   files in `tools/analytics/queries/`, each portable to DuckDB-WASM,
   with an `INDEX.md` codifying what counts as "canonical" so future
   contributors can extend the library without drifting from its
   purpose.
3. **Stay within the ADR-0010 discipline** — every query is SQL
   only; the render layer uses `tabulate` only (no pandas / no
   dataframe library); analytics code lives in `tools/analytics/`,
   outside `src/gradle_deps_monitor/`.
4. **Open Phase 8 — Analytics & insights** in the roadmap and
   promote [RFC-0010](0010-html-export.md) (HTML export) from Backlog
   into the same phase, signaling the dependency direction: HTML
   export will consume the same canonical query layer.

## Non-goals

- **A `gradle-deps-monitor analyze` CLI subcommand.** Would pull
  `duckdb` and `tabulate` into the main install path. Deferred to
  a follow-up RFC if non-Claude-Code users ever ask for it.
- **An `--out file.md` flag** on the skill. Claude (main thread)
  can offer to write the file post-run if the user asks; YAGNI for
  v1.
- **A `--query <name>` filter.** v1 always runs all 8 canonical
  queries; selective execution is a v2 concern.
- **Analytics on `freeze-diff.json`.** Phase 8 v1 covers `check`
  outputs only. Diff analytics belongs to a separate RFC.
- **A browser-time / HTML report.** Belongs to RFC-0010; this RFC
  only preserves the option (portable `.sql` files, DuckDB-WASM-ready)
  without committing to it.
- **Polars (as an alternative to DuckDB).** Considered in
  ADR-0010 and rejected for v1.

## Proposed solution

### Architecture (per ADR-0010)

```
.claude/skills/analyze-freeze/
└── SKILL.md                    # frontmatter + procedure Claude follows

tools/analytics/                # downstream tooling — outside src/
├── README.md                   # what this folder is, how to run by hand
├── runner.py                   # CLI: load CSVs, run queries, render Markdown
├── schema.sql                  # CREATE TABLE inventory + findings (typed)
├── render.py                   # tabulate-based Markdown emitter (presentation only)
└── queries/
    ├── INDEX.md                # registry + "what counts as canonical"
    ├── 01_top_risk.sql                       # PR1 (this RFC)
    ├── 02_drift_by_severity.sql              # PR2
    ├── 03_compound_security_duplicates.sql   # PR2
    ├── 04_unstable_prerelease_in_prod.sql    # PR2
    ├── 05_inactive_or_unhealthy.sql          # PR2
    ├── 06_license_risk.sql                   # PR2
    ├── 07_finding_severity_breakdown.sql     # PR2
    └── 08_bom_coverage.sql                   # PR2
```

`pyproject.toml` gains `[project.optional-dependencies] analytics =
["duckdb>=1.1,<2.0", "tabulate>=0.9"]`. Install: `pip install -e
".[analytics]"`.

### Runner behaviour

`tools/analytics/runner.py --dir <report-dir>`:

1. Resolve `<report-dir>` to an absolute path.
2. Verify `freeze-inventory.csv` and `freeze-findings.csv` exist;
   error with a pointer to RFC-0017 + `gradle-deps-monitor check`
   if not.
3. **Header check** — read line 1 of each CSV, compare against the
   expected column list (mirrored in `schema.sql`). On mismatch,
   fail fast with a pointer to RFC-0017 and `schema.sql`. This is
   the substitute for the explicit `schema_version` field that
   RFC-0017 declined.
4. Load both CSVs into in-memory DuckDB tables via `schema.sql`.
5. Glob `queries/*.sql`, execute each in numeric order, hand the
   `DuckDBPyRelation` to `render.py` for the section.
6. Emit a single Markdown document to stdout: one `## <Title>`
   section per query, in numeric order.
7. Exit 0 on success.

Edge cases v1 handles explicitly:

- **Empty CSV** (header only) → empty table; section renders
  "> No rows for this query against this report."
- **Scanner-not-run sentinels** (empty cells in `risk_score`,
  `usage_count`, `vulnerability_count`) → DuckDB infers `NULL`;
  queries gate with `IS NOT NULL`; section adds
  "> Scanner not run — re-run with `--risk-score` / `--module-usage`
  / a CVE token."
- **CSV header drift** → fail-fast with explicit pointer to
  `schema.sql` and RFC-0017.
- **Path with spaces** → `pathlib.Path` throughout; skill quotes
  the arg in the Bash invocation.

### The skill itself

`.claude/skills/analyze-freeze/SKILL.md` frontmatter:

```yaml
---
name: analyze-freeze
description: Run canonical DuckDB queries against a gradle-deps-monitor
  freeze report directory (freeze-inventory.csv + freeze-findings.csv)
  and produce a Markdown insight summary. Use when the user wants to
  "analyze", "explore", "dig into", or "get insights from" a freeze
  report directory, or after a `gradle-deps-monitor check` run when
  the user wants more than the standard freeze.md.
---
```

Body sections (mirroring `.claude/agents/housekeeper.md` tone):

1. **What this skill does** — 3 lines.
2. **When to invoke** — bullets aligned with description triggers.
3. **Inputs** — one positional path arg.
4. **Procedure** — resolve abs path, verify CSVs, run
   `python tools/analytics/runner.py --dir <abs>`, summarise the
   top 3–5 observations (citing section names; not paraphrasing
   tables), offer next actions ("write to `<dir>/analysis.md`?").
5. **Hard constraints** — read-only against input CSVs; the only
   allowed shell is `runner.py`; never re-implement query logic
   in-head if `runner.py` fails.
6. **Troubleshooting** — missing CSV (RFC-0017 pointer);
   `ModuleNotFoundError: duckdb` (`pip install -e ".[analytics]"`);
   "Scanner not run" sections (opt-in flag pointers). PR1 keeps
   troubleshooting minimal; PR2 expands.
7. **Why this skill exists** — 3 lines.

### Canonical query library (8 queries)

Column names verbatim from [RFC-0017](0017-csv-export.md).

| # | Name | Purpose | Columns / shape |
|---|---|---|---|
| 01 | `top_risk` | Top 15 by `risk_score DESC` with `drift`, `vulnerability_count`, `license_tier` | `SELECT … FROM inventory WHERE risk_score IS NOT NULL ORDER BY risk_score DESC LIMIT 15` |
| 02 | `drift_by_severity` | `drift × risk_level` bucket counts | `GROUP BY drift, risk_level → COUNT(*)`, pivoted |
| 03 | `compound_security_duplicates` | Duplicates where one copy has CVEs (RFC-0017 issue-#13) | Self-join `inventory` on `coordinate` |
| 04 | `unstable_prerelease_in_prod` | Pre-release tiers in catalog | `WHERE stability_tier IN ('alpha','beta','rc','pre_1_0','snapshot','dev','unknown')` |
| 05 | `inactive_or_unhealthy` | Libraries not flagged `active` | `WHERE health_status != 'active'` |
| 06 | `license_risk` | Non-permissive / unknown licenses | `WHERE license_tier IN ('weak_copyleft','strong_copyleft','proprietary','unknown')` |
| 07 | `finding_severity_breakdown` | Findings distribution | `findings GROUP BY section, common_severity → COUNT(*)` |
| 08 | `bom_coverage` | BoM cohort sizes + outliers | `GROUP BY bom_parent` + heuristic outlier list |

Coverage check: every distinct CSV dimension (risk, drift, stability,
health, license, usage, BoM, duplicates, findings) is touched by at
least one canonical query.

### Definition of "canonical"

Codified in `tools/analytics/queries/INDEX.md`. A query is
canonical iff it satisfies **all four**:

1. **Generalizable** — answers a question any Android project could
   ask, not specific to one corpus or team.
2. **Repeatable insight** — a reviewer asks this every freeze, not
   once.
3. **Compresses signal** — output is shorter than the raw CSV slice
   it queries; a "show me everything" query is not canonical.
4. **Self-contained SQL** — single `SELECT` (CTEs OK) against the
   two declared tables, no DuckDB-only extensions that won't
   survive a port to DuckDB-WASM.

Soft signals (nudge toward canonical, don't decide alone): pairs
with an existing `freeze.md` section; uses a column other queries
don't (broadens coverage); answers a question the maintainers
heard twice.

Process for adding a query (also in `INDEX.md`):

1. Validate against the 4 criteria.
2. Add `NN_<name>.sql` (next number, snake_case name).
3. Add a row to the `INDEX.md` registry: `name | purpose | columns
   touched | what it tells you`.
4. If the query introduces a new column reference or enum value,
   update `schema.sql` to match.
5. Manual run via `python tools/analytics/runner.py --dir
   reports/sunflower-2026-05-19/` confirms the new section appears.

### Tracer-bullet shape (per ADR-0009)

Two PRs:

**PR1 — tracer.** Lands ADR-0010, this RFC, full scaffolding under
`tools/analytics/`, the skill stub at
`.claude/skills/analyze-freeze/SKILL.md`, **one** end-to-end query
(`01_top_risk.sql`), a skeletal `queries/INDEX.md`, the new Phase 8
row in `docs/roadmap.md` (with RFC-0010 promoted from Backlog), the
`[analytics]` optional extra in `pyproject.toml`, and a CHANGELOG
entry under `[Unreleased] / Added`. Manual smoke test against
`reports/sunflower-2026-05-19/`.

**PR2 — fill.** Remaining 7 canonical queries, polished `render.py`
with empty-result + "scanner not run" handling, expanded
troubleshooting in `SKILL.md`, new
`docs/user-guide/analyzing-a-freeze-report.md` (skill primer + worked
Sunflower example), README pointer, `CONTRIBUTING.md` reading-order
updated. Mark RFC-0033 Implemented + Phase 8 ✅ Closed (v1) in
roadmap. CHANGELOG entry.

### Alternatives considered

1. **DuckDB + pandas (with pandas confined to render).** Originally
   the proposed stack — pandas 2.x pulled `tabulate` transitively,
   so the dep cost looked like one package. Falsified during the
   tracer: pandas 3.x dropped that transitive pull, so `tabulate`
   would have to be declared explicitly anyway. With `tabulate`
   explicit, pandas was reduced to wrapping a one-line render call
   in a DataFrame round-trip. Dropped in favour of DuckDB +
   tabulate direct; ADR-0010 documents the pivot and leaves a hook
   to reconsider pandas at RFC-0010 (HTML export) time, where
   build-time data shaping may earn it back.
2. **Pandas-as-compute** — rejected by [ADR-0010](../adr/0010-analytics-stack-duckdb.md):
   blocks the WASM port that makes the future HTML report cheap.
3. **`gradle-deps-monitor analyze` CLI subcommand** — would pull
   `duckdb` and `tabulate` into the main install path for everyone.
   Deferred; revisit if the skill proves valuable enough that
   non-Claude-Code users demand a CLI path.
4. **Sub-agent instead of skill** — rejected because the work is
   parameterised by a directory argument and lives entirely in
   stdout, not in a freeform task that benefits from a fresh
   context. Sub-agents earn their cost when the work is bounded,
   repeatable, and worth running on a cheaper model
   (`housekeeper`/`test-runner`); `/analyze-freeze` is none of
   those — its value is the canonical queries + runner contract,
   not isolation.
5. **`uv run --with duckdb --with tabulate python tools/analytics/runner.py …`**
   instead of installing the `[analytics]` extra — clever (works
   on a clean clone without `pip install`), but introduces `uv` as
   a new tool dependency the project hasn't adopted elsewhere.
   Rejected for v1; the conventional extra is consistent with the
   existing `[dev]` pattern.
5. **Names `/inspect-freeze`, `/freeze-xray`, `/freeze-insights`**
   — `/analyze-freeze` chosen for tone consistency with
   `housekeeper` and `test-runner` (direct verbs, no metaphors).
   `/freeze-xray` was the most evocative alternative; revisit if
   the skill ever expands beyond the current scope (e.g. diff
   analytics would push toward a more generic name).

## Definition of done

- [x] PR1 lands ADR-0010 + this RFC + `tools/analytics/` scaffold +
  skill stub + `01_top_risk.sql` + skeletal INDEX.md + Phase 8
  roadmap row + `[analytics]` extra + CHANGELOG entry.
- [x] PR1 smoke test: `python tools/analytics/runner.py --dir
  reports/sunflower-2026-05-19/` exits 0, prints a Markdown document
  with one `## Top risk` section, top row is one of `androidx-compose-*`
  (risk_score 28).
- [x] PR1 skill invocation: `/analyze-freeze reports/sunflower-2026-05-19/`
  in Claude Code resolves the path, runs the runner, surfaces a
  1–2 sentence summary citing top-risk libraries, doesn't write
  any files.
- [x] PR2 lands queries 02–08, render polish, User Guide page,
  README pointer, CONTRIBUTING reading-order update.
- [x] PR2 verification on `reports/sunflower-2026-05-19/`:
  - All 8 sections present in stdout.
  - `compound_security_duplicates` renders "no rows" (Sunflower
    has none) — confirms empty-result rendering.
  - `inactive_or_unhealthy` lists `junit:junit`.
  - `unstable_prerelease_in_prod` lists `material 1.13.0-alpha01`,
    `glide 1.0.0-beta01`, `accompanist-systemuicontroller 0.34.0`
    (pre_1_0), `androidx-paging-compose 3.3.0-rc01`.
  - `license_risk` lists `junit` (weak_copyleft) + `guava` (unknown).
  - `finding_severity_breakdown` totals match the 10 data rows in
    `freeze-findings.csv`.
- [x] `docs/roadmap.md` shows Phase 8 ✅ Closed (v1) with RFC-0033
  ✅ and RFC-0010 📋.
- [x] RFC-0033 status flipped to `Implemented` in PR2.

## Out of scope

- The `gradle-deps-monitor analyze` CLI subcommand (deferred).
- The `--out` and `--query` flags on the skill (deferred to v2).
- Diff-report analytics (separate RFC).
- HTML / browser-time report (RFC-0010, now positioned in Phase 8
  but tracked separately).
- Polars (ADR-0010 alternative). Pandas: deferred per ADR-0010's
  RFC-0010 hook — revisit if the HTML export earns it back at
  build-time.
- Tests in `tests/analytics/`. Analytics is downstream tooling;
  mypy/import-linter scope is unchanged. One optional happy-path
  smoke test in `tools/analytics/` only if `runner.py` grows
  non-trivial logic in PR2.
