# RFC-0017: Comprehensive CSV Export (Inventory & Findings)

**Status:** Draft
**Created:** 2026-05-07
**Related JTBDs:** JTBD-5 (readable report), cross-cutting
**Depends on:** none

## Problem

The current reporting suite (Markdown and Slack) focuses on human readability and concise summaries. While effective for quick reviews, it has two major drawbacks in large projects:

1.  **Data Loss in Summaries:** To keep the report clean, we only show the "Top 10" in sections like Risk Score or Module Usage. Deep-dive analysis of all 170+ libraries requires parsing the machine-readable JSON manually.
2.  **Lack of Actionable Flat Log:** Findings (errors, warnings) are scattered across multiple sections. A developer wanting to "fix everything" has to scroll through the entire report to find disparate tasks.

## Proposed solution

Introduce two new infrastructure writers that generate flat CSV files. These files act as the "technical audit trail" and serve as a structured input for spreadsheets or future HTML views.

### 1. `inventory.csv` (Library-Centric)

A flattened, multidimensional table where each row represents one library from the catalog.

**Columns:**
- `alias`: Catalog alias.
- `coordinate`: `group:artifact`.
- `version`: Pinned version.
- `latest_stable`: Latest resolved version from Maven.
- `drift`: `none`, `patch`, `minor`, `major`.
- `risk_score`: Total risk score (0-100).
- `risk_level`: `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`.
- `usage_count`: Number of modules directly using the library.
- `vulnerability_count`: Count of active CVEs.
- `compliance_issues`: IDs of failed compliance rules.
- `license_tier`: `PERMISSIVE`, `STRONG_COPYLEFT`, etc.
- `health_status`: `ACTIVE`, `DEPRECATED`, `ABANDONED`.
- `bom_parent`: Alias of the managing BoM, if any.

### 2. `findings.csv` (Event-Centric)

A flat log of every warning, error, and informational finding detected across the entire run.

**Columns:**
- `section`: Originating section (e.g., `Security`, `Toolchain`, `Catalog Health`).
- `rule_id`: Unique identifier of the rule (e.g., `HDX-001`, `TOOL-KC-001`).
- `severity`: Standard severity (`ERROR`, `WARNING`, `INFO`).
- `common_severity`: Unified `CommonSeverity` value.
- `target`: The entity affected (library alias, module path, or "catalog").
- `message`: Human-readable description of the problem.
- `recommendation`: Suggested fix or next steps.

## Implementation Plan

### Phase 1: Infrastructure Adapters
- Create `src/gradle_deps_monitor/infrastructure/writers/csv_writer.py`.
- Implement `InventoryCsvWriter` and `FindingsCsvWriter` using the standard `csv` module.
- Ensure proper escaping and UTF-8 encoding.

### Phase 2: Wiring
- Update `src/gradle_deps_monitor/bootstrap.py` to include these writers in the `check` command pipeline.
- Filenames: `inventory.csv` and `findings.csv`.

### Phase 3: Verification
- Add unit tests for both writers using mock `FreezeReport` data.
- Verify that opt-out data (like `--risk-score` disabled) results in empty or "N/A" columns instead of crashes.

## Alternatives considered

- **Single Master CSV:** Rejected. Mixing library dimensions with individual findings results in a confusing schema with too many empty cells.
- **Excel (.xlsx) Export:** Rejected. CSV is simpler to implement, version-control friendly, and more portable for CI environments.
