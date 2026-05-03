# RFC-0010: HTML export

**Status:** Proposed
**Created:** 2026-05-03
**Related JTBDs:** JTBD-5
**Depends on:** Markdown / JSON output (Phase 1)

## Problem

The canonical output of the tool is Markdown
([ADR-0002](../adr/0002-markdown-as-canonical-output-format.md)),
which is ideal for committing alongside the codebase and for
GitHub diff views. It is not ideal for:

- Sharing with non-technical stakeholders who do not navigate
  GitHub
- Visualizing trends (charts of risk score over time, per-module
  dependency counts)
- Producing a self-contained file that renders consistently when
  emailed or attached to a release

An HTML export addresses these cases without compromising the
canonical Markdown format.

## Proposed solution

Add an `--html` flag that produces a self-contained HTML file
alongside the Markdown and JSON outputs.

The HTML report is generated from the JSON snapshot, ensuring
that all three representations describe the same underlying data.
This avoids drift between formats.

The HTML includes:

- The same content as the Markdown, rendered with light styling
- Inline charts for trends (when historical data is available):
  - Risk score evolution
  - Outdated dependency count over time
  - CVE count over time
- A table of contents with anchor links

The output is a single file with all CSS / JavaScript inlined, so
it can be emailed or attached to a release artifact without
external dependencies.

## Alternatives considered

- **HTML as the primary format**: rejected — HTML diffs poorly
  in version control and is not as scannable in raw form. See
  [ADR-0002](../adr/0002-markdown-as-canonical-output-format.md).
- **Markdown rendered to HTML on demand by GitHub**: works for
  in-repo viewing but does not support charts or work outside of
  GitHub.
- **PDF export instead of HTML**: PDF is non-diffable and harder
  to generate without binary dependencies. HTML is preferable as
  an output, and users can print to PDF themselves.

## Cost estimate

Small. ~1-2 days, deferred until enough freeze history exists to
make the chart features meaningful:

- HTML template with inlined CSS
- Chart rendering via a lightweight library (e.g., Chart.js
  inlined, or a pre-rendered SVG approach)
- Self-contained build (no external CDN references)

## Success metrics

- HTML output renders correctly in current Chrome, Firefox, and
  Safari without external assets
- Charts only appear when at least two historical reports exist
  in `freeze-reports/`
- HTML, Markdown, and JSON outputs always describe the same
  dependency state for a given run
