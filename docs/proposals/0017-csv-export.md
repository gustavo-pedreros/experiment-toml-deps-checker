# RFC-0017: Comprehensive CSV Export (Inventory & Findings)

**Status:** Implemented
**Created:** 2026-05-07
**Revised:** 2026-05-17 (post stress-test menu; post RFC-0019 through RFC-0027)
**Shipped:** PR #58 (tracer, 2026-05-17) + PR #59 (enrichment + findings, 2026-05-18)
**Related JTBDs:** JTBD-5 (Technical Audit Trail), cross-cutting
**Depends on:** RFC-0026 (PRE_1_0 stability tier — exposed in inventory column)
**Cross-cuts:** issue #6, #13 from the 2026-05 stress-test menu (see "Stabilisation links" below)

## Problem

The current reporting suite (Markdown, JSON, Slack) focuses on
human readability and concise summaries. While effective for quick
reviews, it has three drawbacks for larger projects (170+ libraries
in the validation corpus):

1. **Data loss in summaries.** Sections like Risk Score and Module
   Usage paginate to "Top 10" for readability. Deep-dive analysis
   of every library requires parsing the JSON manually.
2. **No flat actionable log.** Findings (errors, warnings) are
   scattered across multiple Markdown sections. A developer wanting
   to "fix everything" has to scroll through the entire report and
   manually correlate.
3. **Cross-section signal lost in narrative format.** Concrete
   example from the stress test (issue #13): the catalog has
   `core_okhttp 5.3.2` + `legacy_okhttp 4.2.2` → Catalog Health
   flags duplicate; Security separately flags a CVE on the older
   version. Both findings are correct individually, but the
   compound story ("the duplicate is the reason you're exposed to
   the older CVE") requires manual correlation. A flat
   per-library row with every dimension joined makes the compound
   visible at-a-glance.

## Proposed solution

Two new infrastructure writers that generate flat CSV files.
Together they form a "technical audit trail" that consumers can
ingest into spreadsheets, BI tools, or future HTML views.

### 1. `inventory.csv` (library-centric, one row per catalog library)

Every library in the catalog becomes one row, with every dimension
(version, drift, CVE count, license tier, BoM parent, duplicates,
etc.) joined into a single record. This is the cross-section view
that issue #13 was asking for.

**Columns (final, post-stress-test):**

| Column | Type | Notes |
|---|---|---|
| `alias` | str | Catalog alias |
| `coordinate` | str | `group:artifact` |
| `version` | str | Pinned version |
| `stability_tier` | str | `stable` / `pre_1_0` / `rc` / `beta` / `alpha` / `dev` / `snapshot` / `unknown` — surfaces RFC-0026's new PRE_1_0 distinct from STABLE |
| `latest_stable` | str | Latest resolved version from Maven (post-RFC-0027 stability gate) |
| `drift` | str | `none` / `patch` / `minor` / `major` / `unknown` |
| `risk_score` | int | 0-100; empty cell when `--risk-score` not enabled |
| `risk_level` | str | `LOW` / `MEDIUM` / `HIGH` / `CRITICAL` / `NONE`; empty when risk score disabled |
| `usage_count` | int | Direct dependencies across scanned modules; empty when `--module-usage` not enabled |
| `vulnerability_count` | int | Active CVEs from GHSA scanner; empty when scanner not injected |
| `compliance_issues` | str | Comma-separated rule IDs (e.g. `PSC-TARGET-SDK,PSC-MIN-SDK`) |
| `license_tier` | str | `permissive` / `weak_copyleft` / `strong_copyleft` / `unknown` |
| `health_status` | str | `active` / `deprecated` / `relocated` / `inactive` (derived from `LibraryHealthFinding.signal`) |
| `bom_parent` | str | Alias of the managing BoM, empty when none |
| `duplicate_of` | str | Comma-separated other aliases sharing the same `group:artifact`; empty when unique |

**Empty cell semantics:** empty = "this dimension didn't run / not
applicable" (e.g. `risk_score` is empty when `--risk-score` flag is
off). Zero = "ran, found zero". This convention covers the CSV
side of issue #5; a follow-up RFC will add explicit `*_scanned`
flags to the JSON / Markdown reports for full parity.

### 2. `findings.csv` (event-centric, one row per finding)

Flat log of every warning, error, and informational finding
detected across the entire run, regardless of originating section.

**Columns:**

| Column | Type | Notes |
|---|---|---|
| `section` | str | Originating section (e.g. `Security`, `Toolchain`, `Catalog Health`, `Compliance`, `Library Health`, `Module Usage`, `License`, `Changelog`) |
| `rule_id` | str | Stable rule identifier (e.g. `HDX-001`, `TOOL-KC-001`, `catalog.duplicate-library`, `GHSA-xxxx-xxxx`) |
| `severity` | str | Section-native severity (`ERROR` / `WARNING` / `INFO` / advisor severity) |
| `common_severity` | str | Unified severity per `CommonSeverity` (post-RFC-0016) |
| `target` | str | Affected entity: library alias, module path, `catalog`, or coordinate |
| `message` | str | Human-readable description |
| `recommendation` | str | Suggested fix, when the finding type carries one |

## Stabilisation links

This RFC is the natural answer to two of the four pending
stress-test menu items:

- **Issue #13 (cross-section linking)**: `inventory.csv` makes the
  compound story visible by joining `vulnerability_count` +
  `duplicate_of` (and every other dimension) in a single row.
  No additional cross-section dependency model needed in the
  domain — the join lives in the CSV writer, computed at
  serialisation time.
- **Issue #6 (BoM children duplicate top-10)**: `inventory.csv` is
  flat, no top-N pagination. Readers filter by `bom_parent =
  compose_bom` in Excel/Sheets and see the cohort grouped
  naturally. The Markdown top-10's BoM-children noise becomes a
  smaller concern because anyone doing serious analysis has a
  better tool.

The remaining stress-test menu items (#5 empty sections elision,
#7 console "N other" template) are unrelated to CSV and are tracked
for a small follow-up RFC.

## Tracer Bullet Path (ADR-0009)

End-to-end integration is validated before committing to all 15
columns.

### PR #1 — Inventory tracer

- New `InventoryCsvWriter` in `infrastructure/writers/inventory_csv_writer.py`.
- Three initial columns only: `alias`, `coordinate`, `version`.
- Registered in `bootstrap.py:create_check_command` alongside the
  existing three writers.
- Output filename: `freeze-inventory.csv`.
- Uses Python's stdlib `csv` module with `csv.writer` + `QUOTE_MINIMAL`
  (Excel-compatible default). UTF-8 with BOM is **rejected** —
  modern Excel and Sheets both read UTF-8 without BOM; the BOM
  trips up Python consumers.
- Tests: file created, header row matches column list, content
  correctly escaped (commas in messages, quotes, newlines).
- CHANGELOG entry under `[Unreleased] / Added`.

### PR #2 — Inventory enrichment + findings.csv

- Fill in the remaining 11 inventory columns (using `FreezeReport`
  data; no new ports / adapters / domain changes).
- New `FindingsCsvWriter` in
  `infrastructure/writers/findings_csv_writer.py`.
- Output filename: `freeze-findings.csv`.
- Iterates every finding-shaped collection on `FreezeReport`
  (`health_findings`, `compliance_findings`, `toolchain_findings`,
  `library_health_findings`, security `LibraryAdvisory` rows,
  license non-permissive findings, changelog BREAKING entries).
  Uses `common_severity` from the post-RFC-0016 unified hierarchy.
- `duplicate_of` column computed at write time by grouping
  `catalog.libraries` on `(group, artifact)`. No domain change.
- Tests: per-section finding flow covered with a hand-rolled
  `FreezeReport` fixture that includes one entry from each
  section.
- CHANGELOG entry under `[Unreleased] / Added`.

## Implementation Plan

Two PRs total. Both small, both contained to infrastructure layer.

### PR #1 cost estimate

~50 LoC writer + ~30 LoC tests + 3 lines in bootstrap + CHANGELOG.

### PR #2 cost estimate

~120 LoC of writer logic (column enrichment) + ~60 LoC findings
writer + ~80 LoC of tests + CHANGELOG.

## Schema impact

`none` to existing schemas. The CSV outputs are new files; their
columns become a new external surface but are not versioned via
`schema_version` (CSV consumers traditionally tolerate column
order changes, and we will document the ordering as stable). If
future evolution demands strict versioning, a header row prefixed
with `# schema-version: 1.0.0` is the standard escape hatch.

## Alternatives considered

- **Single master CSV** (one row per `(library, finding)` pair).
  Rejected — mixes dimensions; many empty cells; not Excel-friendly.
- **Excel (.xlsx) export**. Rejected — CSV is simpler, version-
  control friendly, more portable for CI environments. Excel
  consumers open CSV just fine.
- **JSON-Lines (ndjson) instead of CSV.** Rejected — ndjson is
  programmer-friendly but loses the Excel-paste use case which is
  the primary value driver for end users (auditors, security
  reviewers).
- **HTML export instead of CSV.** RFC-0010 (HTML export) is in the
  backlog and could subsume some of this. Not subsumed because:
  (a) RFC-0010 is presentation, CSV is interchange; (b) any future
  HTML export will likely ingest the JSON, not the CSV.
- **Add a "duplicate_of" column to JSON instead of CSV-only.**
  Reasonable but deferred — the JSON is already verbose; if
  consumers need this they'd join JSON manually too. The CSV's
  flat shape is the right place for the convenience join.

## Validation Strategy

Post-PR #2 merge: re-run against `nowinandroid` (small, public
corpus) and the 170-library fintech-style corpus. Confirm:

- `freeze-inventory.csv` has exactly one row per catalog library
- Both Excel and Google Sheets open the file without encoding
  warnings or column misalignment
- For `nowinandroid` post-RFC-0027 (`com.google.protobuf:protoc`):
  `latest_stable` column shows the 4.x.y line, not `21.0-rc-1`
- For the fintech-style corpus: `duplicate_of` column lights up
  for `core_okhttp` ↔ `legacy_okhttp` (the issue #13 case)

## Rollback strategy

Revert each PR independently. PR #1 revert removes `inventory.csv`
from the output directory. PR #2 revert reverts inventory back to
its 3-column tracer + removes `findings.csv`. Downstream consumers
that depend on either file see the absence and either fall back to
JSON or surface a clear error.

## PR budget

**2 PRs** from tracer to DoD.

## Definition of Done (DoD)

### PR #1 (tracer)
- [ ] **Integration**: `freeze-inventory.csv` written to the
  output directory on every `check` run.
- [ ] **Architecture**: Writer registered in the **Composition
  Root** (`bootstrap.py:create_check_command`).
- [ ] **Testing**: File creation + header row + minimal content
  + CSV escaping covered by integration tests.
- [ ] **Documentation**: CHANGELOG entry.

### PR #2 (enrichment + findings)
- [ ] **All 15 inventory columns populated** with correct
  empty-cell semantics.
- [ ] **`freeze-findings.csv` written** with one row per finding
  across all sections.
- [ ] **`duplicate_of` cross-section join** verified against the
  validation corpus.
- [ ] **Both files parseable** by Excel and Google Sheets without
  encoding warnings.
- [ ] **CHANGELOG entries** for both writers + the enriched
  inventory.
