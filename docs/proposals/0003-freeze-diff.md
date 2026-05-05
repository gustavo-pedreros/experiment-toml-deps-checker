# RFC-0003: Diff between freeze reports

**Status:** Shipped — domain, use case, JSON loader (Step 11) + diff writers, CLI command, Rich console (Step 12)
**Created:** 2026-05-03
**Related JTBDs:** JTBD-5
**Depends on:** Markdown / JSON output (Phase 1)

## Problem

Each freeze report describes the project at a single point in
time. The strategic value emerges when reports are compared across
time: how much technical debt was paid down, which CVEs were
introduced, whether the team is upgrading or accumulating drift.

Today, comparing two freezes requires a human to read both reports
side by side. There is no first-class tooling.

## Proposed solution

Introduce a `diff` command that takes two freeze reports (typically
two JSON snapshots) and produces a comparative report in Markdown
and JSON.

```
toml-deps-checker diff freeze-reports/2026-04-18-def456.json \
                       freeze-reports/2026-05-02-abc123.json
```

The diff report highlights:

- Dependencies upgraded, added, or removed
- New CVEs introduced and CVEs resolved
- Compliance status changes (e.g., target SDK moved from 33 to 34)
- Risk trend (when the score is enabled across both reports)
- Toolchain consistency changes

Example output section:

```
📊 Diff: freeze-2026-04-18 → freeze-2026-05-02

Dependencies
   Upgraded: 23 (1 major, 18 minor, 4 patch)
   Added:     5
   Removed:   2

Security
   New CVEs:        1 critical, 3 medium
   Resolved CVEs:   2 high, 1 medium

Compliance
   Target SDK 33 → 34 ✅ (passed upcoming deadline)

Risk (when enabled)
   Average score: 47 → 42 (improving)
   Top mover:     dagger-android (76 → 51)
```

### First-run handling

When no previous freeze exists, the report still runs and includes
a baseline section in place of the diff:

```
🌱 Baseline established
   This is the first registered freeze report.
   Future reports will compare trends against this baseline.
   Recommendation: review the "Top 10 Risk-Weighted" section as a
   starting point to prioritize technical debt for the next cycle.
```

This means the tool never errors on the absence of history.

## Alternatives considered

- **Embedding diff into every report run**: reject — diff is a
  separate concern, and not every run has two reports to compare.
  Keeping it as a distinct subcommand is cleaner.
- **Diffing Markdown files directly with `git diff`**: works for
  humans browsing PRs, but does not produce a structured comparison
  (added vs removed vs upgraded).

## Cost estimate

Small to medium. ~2 days. The JSON output already carries a
`schema_version`, so the diff loader can be defensive across schema
versions if needed.

## Success metrics

- Diff between two well-formed reports completes in under 1 second
- Diff output gracefully handles schema drift (older snapshots
  still produce useful diffs against newer ones)
- First-run baseline message appears whenever no previous report
  is found at the configured location
