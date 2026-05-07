# RFC-0016: Unified report style (severity + row layout)

**Status:** In progress — 16a shipped, 16b pending
**Created:** 2026-05-06
**Related JTBDs:** JTBD-5 (readable report), cross-cutting
**Depends on:** all shipped sections (catalog health, library
health, compliance, security, toolchain, license, risk score)

## Problem

Each section ships its own severity enum and its own rendering
choices. Side-by-side this looks chaotic to readers:

| Section          | Severity enum             | Console example   |
|------------------|---------------------------|-------------------|
| Catalog Health   | `Severity` (`finding.py`) | `error` (lower, dim) |
| Library Health   | `LibraryHealthSeverity`   | `HIGH` (red bold) |
| Compliance       | `ComplianceSeverity`      | `ERROR` (red bold) |
| Toolchain        | `ToolchainSeverity`       | `error` (lower, red) |
| License          | tier-based, no severity   | inline label      |

Row layouts are equally heterogeneous: bullets `•`, brackets
`[ID-001]`, varying indents and column widths. A reviewer
skimming the report cannot infer "this is the most urgent line"
from visual hierarchy alone — they have to read every section's
local conventions.

## Proposed solution

A single common-severity model + a single rendering helper used
across the console, Markdown writer, and Slack writer.

The work splits cleanly into two PRs that share one module.

### Sub-RFC 16a — `CommonSeverity` and central style mapping

Domain layer:

```python
# domain/severity.py
class CommonSeverity(StrEnum):
    ERROR      = "error"
    WARNING    = "warning"
    INFO       = "info"
    SUGGESTION = "suggestion"
```

Each existing severity enum gains a `to_common(self) ->
CommonSeverity` method. This preserves domain vocabulary
(`ToolchainSeverity.ERROR` stays meaningful in toolchain code)
while giving presentation a single dial.

Presentation layer:

```python
# presentation/severity_style.py
@dataclass(frozen=True)
class SeverityStyle:
    label: str          # "ERROR", "WARN", "INFO", "TIP"
    rich_style: str     # Rich style string, e.g. "bold red"
    md_emoji: str       # "🔴", "🟡", "🔵", "💡"
    slack_emoji: str    # ":red_circle:", ":warning:", ":information_source:", ":bulb:"

STYLE: dict[CommonSeverity, SeverityStyle] = {...}
```

All sections import from this module instead of declaring
private style dicts.

### Sub-RFC 16b — Unified row helper

A shared row contract:

```
[SEVERITY ] subject              · message               · extra
↑           ↑                     ↑                       ↑
fixed       cyan bold             neutral                 muted
width 10
```

Console:

```python
# presentation/console.py
def print_finding_row(
    severity: CommonSeverity,
    subject: str,
    message: str,
    *,
    extra: str | None = None,
) -> None: ...
```

Writer parity:

- **Markdown**: every section's table uses the same column
  contract: `| Severity | Subject | Message | Extra |`. Tables
  share a small helper (`_render_findings_table`).
- **Slack**: each finding becomes a `mrkdwn` block prefixed with
  the section's `slack_emoji`. Blocks share a builder.
- **JSON**: every finding-shaped object gains a
  `"common_severity": "error"` field for downstream tooling that
  wants to dashboard across sections.

### Schema bump

Per [ADR-0008](../adr/0008-json-schema-semver.md): MINOR bump
(new additive `common_severity` field on existing finding
objects).

## Alternatives considered

- **Collapse all section-specific severity enums into a single
  enum**: rejected. Each domain has legitimate vocabulary
  (`LibraryHealthSeverity.HIGH` is not the same concept as
  `ComplianceSeverity.ERROR`); the adapter pattern via
  `to_common()` keeps semantics local while unifying
  presentation.
- **Fix only the console without touching writers**: rejected.
  JSON consumers (CI dashboards, Slack readers) see the same
  inconsistency. Half-measure.
- **Restyle on the way out of the writer rather than introducing
  a domain enum**: rejected. Style maps would need to grow an
  entry per source severity, multiplying maintenance.

## Cost estimate

- **16a — CommonSeverity + central style**: ~1 day. Enum,
  mappers on each existing enum, central style module, snapshot
  tests for the mapping.
- **16b — Row helper + writer parity**: ~1.5 days. Console
  refactor, three writers, regenerate fixtures, update tests.

Total: ~2.5 days, ideally two PRs (16a then 16b).

## Success metrics

- Same finding severity renders **identically** across console,
  Markdown, Slack — confirmed by side-by-side review of a real
  freeze report.
- Skim test: a hand-reviewed report with 30+ findings shows clear
  visual hierarchy; reviewer can rank-order severities at a
  glance without reading text.
- All existing tests still pass after refactor (no behaviour
  regression — purely stylistic).
- `presentation/severity_style.py` is the only place style
  decisions live; `grep` for hardcoded style strings in writers
  returns nothing.
