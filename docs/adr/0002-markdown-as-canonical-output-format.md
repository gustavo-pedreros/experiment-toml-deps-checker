# ADR-0002: Markdown as the canonical output format

## Status

Accepted — 2026-05-03

## Context

The freeze report needs to live somewhere durable. The current tool
emits a JSON file and posts a Slack message; nothing is persisted
beyond Slack history.

The intended use case is to commit each freeze report into the repo
under `freeze-reports/`, and to optionally attach the report to the
release tag once the freeze passes QA and ships to production.

Several output formats were considered as the canonical persisted
form:

- **JSON only**: programmatic, but unreadable to humans browsing
  the repo. A reviewer cannot scan a freeze report at a glance.
- **HTML**: visually rich, but produces a large file that diffs
  badly across freezes.
- **PDF**: not diffable, requires extra tooling, and adds binary
  blobs to the repo.
- **Markdown**: renders directly in GitHub's UI, diffs cleanly,
  supports tables and emoji status indicators, is small in size,
  and is universally readable in any text viewer.
- **CSV**: thin format with no support for hierarchy or annotations.

## Decision

Markdown is the canonical, human-readable output format. Every
freeze run produces a `.md` file written to `freeze-reports/`.

JSON is produced alongside the Markdown as the machine-readable
companion. The JSON output carries an explicit `schema_version`
field so the tool can evolve without breaking downstream consumers
(diff against previous freezes, dashboards, CI gates).

Slack output is generated as Block Kit JSON tailored to Slack's
rendering, distinct from the canonical Markdown. It is not
considered a persisted artifact.

HTML, PDF, and other formats may be added later as on-demand
exports, but they are derived from the Markdown / JSON
representation rather than being primary outputs.

## Consequences

**Positive**

- Reports are immediately readable in GitHub diff views
- Reports are compact and version-control friendly
- A standard naming convention (`freeze-reports/YYYY-MM-DD-<sha>.md`)
  enables tooling without a database
- Reports remain useful in offline / clone-only contexts

**Negative**

- Markdown's expressiveness is limited compared to HTML; rich
  visualizations (charts, interactive tables) require the future
  HTML export
- Two representations (Markdown + JSON) must be kept in sync; the
  test suite will assert they describe the same underlying data
