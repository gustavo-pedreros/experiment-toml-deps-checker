---
name: analyze-freeze
description: Run canonical DuckDB queries against a gradle-deps-monitor freeze report directory (freeze-inventory.csv + freeze-findings.csv) and produce a Markdown insight summary. Use when the user wants to "analyze", "explore", "dig into", or "get insights from" a freeze report directory, or after a `gradle-deps-monitor check` run when the user wants more than the standard freeze.md.
---

You are running the `/analyze-freeze` skill for the `gradle-deps-monitor`
project. Your job is to produce an insight summary from a freeze report
directory by delegating compute to `tools/analytics/runner.py` (DuckDB
+ canonical query library). You are NOT a freeze generator and you do
NOT edit the input CSVs.

## What this skill does

Given a freeze report directory containing `freeze-inventory.csv` and
`freeze-findings.csv` (produced by `gradle-deps-monitor check`,
RFC-0017, v0.1.0+), it runs every canonical query in
`tools/analytics/queries/` and emits a Markdown summary — one
`## <Title>` section per query.

The architecture is fixed by [ADR-0010](../../../docs/adr/0010-analytics-stack-duckdb.md):
queries live as portable `.sql` files; pandas is confined to the
render layer; analytics deps are opt-in via the `[analytics]` extra.

## When to invoke

- The user says "analyze", "explore", "dig into", or "get insights
  from" a freeze report directory.
- Right after a `gradle-deps-monitor check` run when the user wants
  more than the narrative `freeze.md`.
- The user mentions the canonical query library or asks "what's the
  top risk?" / "what licenses are in this catalog?" against a known
  report directory.

## Inputs

One positional argument: a path to a freeze report directory. The
directory MUST contain both `freeze-inventory.csv` and
`freeze-findings.csv`.

## Procedure

1. Resolve the path argument to an absolute path. If the user gave a
   relative path, resolve it against the current working directory.
2. Verify both `freeze-inventory.csv` and `freeze-findings.csv` exist
   in that directory. If either is missing, stop — explain that these
   files are produced by `gradle-deps-monitor check` (RFC-0017, v0.1.0+).
3. Run the runner via Bash:

       python tools/analytics/runner.py --dir <absolute-path>

   Quote the path if it contains spaces.
4. Capture stdout. If exit code is non-zero, surface stderr to the
   user and stop. Do NOT try to re-implement the query logic.
5. The runner emits a single Markdown document with one `## <Title>`
   section per canonical query. Show that document to the user (do
   not paraphrase the tables — the tables are meant to be read directly).
6. Add a 3–5 sentence executive summary at the top citing section
   names and the most striking observations. Examples of striking:
   - The top-risk row's `risk_score` is in the HIGH/CRITICAL band.
   - Any section renders "no rows" for a scanner-not-run reason.
   - The `compound_security_duplicates` query has a non-empty result
     (this is the RFC-0017 issue-#13 compound story).
7. Offer next actions, e.g.:
   - "Write this summary to `<dir>/analysis.md`?"
   - "Open GitHub issues for the top-risk items?"
   - "Re-run `gradle-deps-monitor check --risk-score` to populate
     scanner-not-run sections?"

## Hard constraints (read first, never violate)

- **Read-only against the input CSVs.** Never modify
  `freeze-inventory.csv` or `freeze-findings.csv`.
- **The only allowed shell is `tools/analytics/runner.py`.** If it
  fails, surface the error — do not try to reproduce the queries
  manually or call DuckDB directly.
- **Don't write any files** unless the user explicitly asks. Steps 5–7
  are about showing and offering, not acting.
- **Don't run `gradle-deps-monitor check`** as part of this skill.
  If the user wants a fresh report, they invoke `check` separately.

## Troubleshooting

- `ModuleNotFoundError: No module named 'duckdb'` (or `pandas`) →
  the `[analytics]` extra isn't installed. Tell the user to run
  `pip install -e ".[analytics]"` from the repo root.
- `freeze-inventory.csv not found` or `freeze-findings.csv not found`
  → the directory isn't a freeze report. Point to
  `gradle-deps-monitor check` (RFC-0017, v0.1.0+).
- `CSV header drift detected` → the RFC-0017 contract changed and the
  runner caught it. Point to `tools/analytics/schema.sql` and
  `docs/proposals/0017-csv-export.md`. Do not edit those files
  yourself; defer to a maintainer.
- A section renders "No rows" with a "Scanner not run" hint → the
  user ran `gradle-deps-monitor check` without the relevant opt-in
  flag (`--risk-score`, `--module-usage`) or without CVE credentials.
  Mention the flag they'd need for that dimension.

## Why this skill exists

The RFC-0017 CSVs are a high-fidelity interchange surface but had no
canonical consumer until this skill. `/analyze-freeze` is the
canonical consumer: a fixed set of questions every reviewer asks of
every freeze, answered the same way every time. See
[RFC-0033](../../../docs/proposals/0033-analyze-freeze-skill.md) for
the design and the full list of canonical queries.
