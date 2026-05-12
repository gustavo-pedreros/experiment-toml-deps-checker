# RFC-0017: Comprehensive CSV Export (Inventory & Findings)

**Status:** Draft
**Created:** 2026-05-07
**Related JTBDs:** JTBD-5 (Technical Audit Trail), cross-cutting
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

## Tracer Bullet Path (ADR-0009)

To validate the end-to-end integration before implementing all 15+ columns, the first PR will consist of:
1. **Infrastructure**: Create a skeletal `InventoryCsvWriter` in `infrastructure/writers/`.
2. **Domain**: Ensure `FreezeReport` has access to the library list (already exists).
3. **Composition Root**: Register the new writer in `bootstrap.py` so an `inventory.csv` file is generated on every run.
4. **Minimal Output**: The initial CSV will only contain two columns: `alias` and `coordinate`.

This confirms that file system operations, permissions, and the wiring in the Composition Root are working correctly.

## Implementation Plan

### Phase 1: Tracer Bullet
- Implement the skeletal writer and wire it in the Composition Root (`bootstrap.py`).
- Verify the file is created in the output directory with minimal columns.

### Phase 2: Exploration (Optional Spike)
- Research handling of special characters and line breaks in CSV cells to ensure Excel compatibility (Python's `csv` module dialects).

### Phase 3: Enrichment
- Add the remaining columns (Risk Score, CVEs, etc.) once the "plumbing" is validated.

## Alternatives considered

- **Single Master CSV:** Rejected. Mixing library dimensions with individual findings results in a confusing schema with too many empty cells.
- **Excel (.xlsx) Export:** Rejected. CSV is simpler to implement, version-control friendly, and more portable for CI environments.

## Success metrics

- `inventory.csv` and `findings.csv` are generated alongside the Markdown report.
- The CSV files are correctly parsed by Microsoft Excel and Google Sheets without encoding issues.

## Definition of Done (DoD)

- [ ] **Integration**: `inventory.csv` is automatically generated when running `check`.
- [ ] **Architecture**: The writer is registered in the **Composition Root** (`bootstrap.py`).
- [ ] **Testing**: Integration tests verify file creation and basic content.
- [ ] **Robustness**: Verified that the exporter does not crash when optional features (Risk Score, Module Usage) are disabled.
- [ ] **Validation**: CSV format is compatible with common spreadsheet software (UTF-8).
ormat is compatible with common spreadsheet software (UTF-8).
