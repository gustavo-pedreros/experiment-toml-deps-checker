# RFC-0010: HTML Export

**Status:** Proposed
**Created:** 2026-05-03
**Related JTBDs:** JTBD-5 (Technical Audit Trail)
**Depends on:** Markdown / JSON output (Phase 1)

## Problem

The canonical output of the tool is Markdown ([ADR-0002](../adr/0002-markdown-as-canonical-output-format.md)), which is ideal for version control and GitHub diff views. However, it is limited for:

- Sharing with non-technical stakeholders who do not navigate GitHub.
- Visualizing trends (charts of risk score over time, per-module dependency counts).
- Producing a self-contained, aesthetically polished file for release artifacts or emails.

## Proposed solution

Add an HTML writer that produces a self-contained, styled report.

### 1. Unified Data Source
The HTML report will be generated from the `FreezeReport` aggregate, ensuring consistency with Markdown and JSON outputs.

### 2. Rich Visualization
- **Trend Charts**: When historical data is available (via `freeze.json` files in `reports/`), render charts for Risk Score, CVE counts, and Outdatedness drift.
- **Interactive Tables**: Searchable and sortable library tables (client-side JS).

### 3. Self-Contained Artifact
All CSS, JS (e.g., Chart.js), and assets will be inlined to ensure the file works offline and without external dependencies.

## Tracer Bullet Path (ADR-0009)

To validate the template engine and wiring before building complex charts:
1. **Infrastructure**: Create `HtmlWriter` using a simple `string.Template` or skeletal Jinja2.
2. **Composition Root**: Register `HtmlWriter` in `bootstrap.py`.
3. **Minimal Output**: The HTML file should render a simple "Freeze Report - [Date]" header and the total count of libraries.

*This confirms that the HTML file is generated correctly in the output directory and wired into the pipeline.*

## Implementation Plan

### Phase 1: Tracer Bullet
- Implement skeletal `HtmlWriter` and wire it in the **Composition Root**.

### Phase 2: Exploration (Optional Spike)
- **Spike**: Evaluate Jinja2 vs. Mako vs. F-strings for performance and maintainability of the large inlined template.
- **Spike**: Test SVG-based sparklines vs. Chart.js for the "Zero Dependency" requirement (weighing bundle size vs. interactivity).

### Phase 3: Enrichment
- Add interactive tables and CSS styling.
- Implement trend line logic using historical snapshots.

## Alternatives considered

- **PDF Export**: Rejected (too heavy, requires binary dependencies).
- **Static Site Generator (Hugo/Eleventy)**: Rejected (overkill, adds external tool requirement).

## Success metrics

- A single `.html` file is produced alongside other reports.
- It opens correctly in all modern browsers without internet access.
- It provides a "Professional" visual summary suitable for stakeholders.

## Definition of Done (DoD)

- [ ] **Integration**: `HtmlWriter` is registered in the **Composition Root** (`bootstrap.py`).
- [ ] **Architecture**: Follows ADR-0006 and ADR-0009 (Tracer Bullets).
- [ ] **Portability**: All assets are inlined; no external CDN calls.
- [ ] **Accuracy**: Data matches the JSON/Markdown outputs exactly.
- [ ] **Testing**: Integration tests verify file creation and non-empty content.
