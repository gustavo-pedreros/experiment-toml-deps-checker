# RFC-0028: Phase 6 Wrap-up — Render Empty Sections + Fix Console Severity Buckets

**Status:** Proposed
**Created:** 2026-05-18
**Related JTBDs:** JTBD-5 (report clarity), JTBD-1 (informed decisions)
**Depends on:** none

## Problem

Two presentation-layer papercuts from the 2026-05 stress test
remain open. Both are correctness-preserving — the underlying data
is right; the rendering loses signal.

### Issue #5 — empty sections elided from Markdown

Seven Markdown sections return `""` when their finding list is
empty, so the entire section is omitted from `freeze.md`:

`_security_section`, `_compliance_section`, `_toolchain_section`,
`_library_health_section`, `_health_section` (Catalog Health),
`_changelog_section`, `_active_rejections_section`.

The reader can't tell `"didn't scan"` from `"scanned, found nothing"`.
Especially confusing for Security — a missing GitHub token elides
the whole section silently, so the report looks identical to a
clean scan.

**Bootstrap observation that narrows the fix:** of the six
finding-shaped sections, **only the vulnerability scanner can
actually be `None` at runtime** (`bootstrap.py:_build_scanner`
returns `None` when no `GITHUB_TOKEN` / OSS Index creds are set).
Compliance, Toolchain, Library Health, Catalog Health, Changelog
adapters are unconditionally constructed in `bootstrap.py`. For
them, "empty findings" always means "scanned, found nothing" —
no domain change is needed; we just need to render a placeholder.

Security is the only section that needs an explicit `scanned`
signal threaded through the domain.

### Issue #7 — console "N other" bucketing loses severity signal

Three console blocks reuse the same template:
`N {severity_a} + M {severity_b} + K other`. When no high-severity
entries exist, everything collapses into the `other` bucket:

- **Risk Score** (`console.py:389`): when no CRITICAL/HIGH, all
  MEDIUM and LOW libraries report as `N other`. Stress test
  example: `Risk Score — 157 other` while the Markdown report
  showed 137 MEDIUM + 20 LOW.
- **Security** (`console.py:151`): same shape; medium/low
  advisories bucket as `other` when no CRITICAL/HIGH advisories
  exist.
- **Major Upgrades** (`console.py:260`): also says `N other`, but
  here "other" is semantically correct — the binary is
  `LIKELY-breaking vs everything-else (CLEAN/UNKNOWN)`. Leave this
  one alone.

The fix: enumerate every populated severity bucket explicitly
rather than collapsing everything-non-top into "other". Templates
remain the same shape — just emit one more part when MEDIUM/LOW
have non-zero counts and CRITICAL/HIGH are zero.

## Proposed solution

### Part 1 — Issue #5: render empty sections (Markdown)

For the **five sections whose adapter is always injected**
(Catalog Health, Compliance, Toolchain, Library Health,
Changelog), replace the `if not findings: return ""` early
return with a one-liner placeholder that mirrors the convention
already established by `_license_section` and
`_module_usage_section`:

```markdown
## Toolchain Compatibility

> ✅ No toolchain compatibility issues detected.
```

Active Rejections stays elided — it's a positive correctness
signal ("the team has forbidden these versions"), not a scan
result. Empty means "no rejections configured," which carries
no actionable signal worth a section header.

For **Security**, render either of two distinct placeholders:

```markdown
## Security

> ⊘ Security scan not configured — set `GITHUB_TOKEN` to enable
> the GitHub Advisory Database integration, or `OSS_INDEX_USER` +
> `OSS_INDEX_API_KEY` to enable Sonatype OSS Index. Re-run to
> populate this section.
```

vs

```markdown
## Security

> ✅ No known security advisories for any pinned version.
```

The distinction needs a new `security_scanned: bool` field on
`FreezeReport`. Set by `GenerateFreezeReport.execute` from
`self._scanner is not None` immediately after Phase 1's fan-out.
Default `False` so existing test fixtures keep working.

### Part 2 — Issue #7: enumerate severity buckets in console

For Risk Score and Security, when CRITICAL and HIGH are both zero
but MEDIUM or LOW are non-zero, emit explicit medium/low parts
instead of `N other`:

```python
# Risk Score (existing → new)
parts = []
if critical:
    parts.append(f"[bold red]{critical} critical[/bold red]")
if high:
    parts.append(f"[bold yellow]{high} high[/bold yellow]")
if medium:
    parts.append(f"[yellow]{medium} medium[/yellow]")
if low:
    parts.append(f"[blue]{low} low[/blue]")
```

Pre-fix: `Risk Score — 157 other`
Post-fix: `Risk Score — 137 medium, 20 low`

For Major Upgrades the existing `N likely breaking, M other`
template stays — `M other` here means "non-breaking" (CLEAN /
UNKNOWN signal) which is the meaningful complement.

## Schema impact

`security.scanned` field already exists in `freeze.json` (since
v1.0). Today it's derived from `len(report.security_advisories) > 0`
— a heuristic that breaks for the degenerate "empty catalog +
scanner ran" case but is otherwise OK. Post-RFC the source becomes
the new `security_scanned` flag directly. Field name + type
unchanged; semantics tightened to be exactly `"the scanner was
injected"`. **No schema-version bump** — the field name, type, and
documented meaning are unchanged; only the source of truth becomes
authoritative.

The remaining JSON section-presence keys (`compliance.finding_count`
etc.) keep their current semantics — `0` means "ran, found
nothing". Same as today; this RFC does not extend the `scanned`
convention to other sections because they don't need it (their
adapters always inject).

## Tracer Bullet Path (ADR-0009)

Single PR, contained to:

- **Domain**: one new optional `bool` field on `FreezeReport`
  (`security_scanned`).
- **Application**: `GenerateFreezeReport.execute` sets the flag.
- **Infrastructure**: `MarkdownWriter` renders 5 + 1 sections
  with placeholders; `JsonWriter` switches to the new flag for
  `security.scanned`.
- **Presentation**: `console.py` enumerates medium/low buckets
  for Risk Score and Security.

No new ports, no new adapters, no domain restructure.

## Implementation Plan

### PR #1 — Single PR closing Phase 6

1. **Domain**: add `security_scanned: bool = False` to
   `FreezeReport`. Update its docstring.
2. **Use case**: `GenerateFreezeReport.execute` sets the flag
   from `self._scanner is not None` after the Phase 1 fan-out
   completes.
3. **JSON writer**: change `security.scanned` source from
   `len(security_advisories) > 0` to `report.security_scanned`.
4. **Markdown writer**: rewrite the 5 always-injected section
   functions to render a "no findings" placeholder when empty
   instead of returning `""`. Rewrite `_security_section` to
   take the `scanned` flag and render the appropriate
   placeholder.
5. **Console**: add medium/low parts to the Risk Score and
   Security bucket templates.
6. **Tests**: add fixtures covering each new rendered placeholder;
   add tests for the bucket enumeration; update any existing
   tests that asserted on absent sections (likely `test_writers`
   `test_markdown_omits_empty_sections` needs adjusting).
7. **CHANGELOG**: entry under `[Unreleased] / Changed` documenting
   the rendering shift + the cleaner `security.scanned` semantics.

## Validation Strategy

Post-merge, re-run against:

- `nowinandroid` (no `GITHUB_TOKEN`): Security section should
  render the "⊘ scan not configured" placeholder explicitly.
- `nowinandroid` (with `GITHUB_TOKEN`, currently 0 advisories):
  Security section should render the "✅ no advisories" placeholder.
- The 170-library fintech corpus (with token + caches cleared):
  console Risk Score line should enumerate medium/low instead of
  `N other`.

## Alternatives considered

- **Add `*_scanned` flags for every section, not just Security.**
  Rejected — bootstrap unconditionally injects the other five
  adapters; the flag would always be True and add noise to the
  data model. Revisit only if/when a section becomes
  conditionally injected.
- **Bump `freeze.json` schema to 1.8.0 for the `security.scanned`
  semantic tightening.** Rejected — field name, type, and
  documented meaning unchanged; only the implementation becomes
  more accurate. No consumer breakage; no schema bump warranted.
- **Show medium/low in the console as "N medium, M low" only
  when no critical/high exists; collapse to "K other" when both
  buckets exist (today's behaviour).** Considered. Rejected for
  consistency — if we're going to enumerate buckets, do it
  always. Readers expect uniform behaviour.

## Cost estimate

Small. ~40 LoC of writer changes + ~15 LoC of console + ~30 LoC
of tests + CHANGELOG. One new bool field on the domain object.
No new dependencies, no port signature changes.

## Success metrics

- **Issue #5 closed**: no section is silently omitted; Security
  distinguishes "not configured" from "scanned-clean".
- **Issue #7 closed**: Risk Score and Security console output
  enumerates medium/low when CRITICAL/HIGH are zero.
- **No regression**: existing test suite stays green (except for
  `test_markdown_omits_empty_sections` which must invert its
  assertion).

## Rollback strategy

Revert the single PR. Sections go back to eliding when empty;
`security.scanned` reverts to the `len(...)` heuristic; console
reverts to `N other`. No schema change to roll back.

## PR budget

Estimated **1 PR** from tracer to DoD.

## Definition of Done (DoD)

- [ ] **Integration**: All 5 always-injected sections render
  placeholders when empty. Security renders distinct
  "not configured" vs "scanned-clean" placeholders. Console
  enumerates medium/low buckets for Risk Score and Security.
- [ ] **Architecture**: Follows ADR-0006 — the
  `security_scanned` flag lives on the domain
  `FreezeReport`, set by the application use case, consumed by
  infrastructure writers.
- [ ] **Testing**: New tests cover each placeholder, the
  `security_scanned` flag setting, and the console bucket
  enumeration. The `test_markdown_omits_empty_sections` test is
  inverted to assert that sections are now rendered.
- [ ] **Documentation**: CHANGELOG entry documents both the
  rendering shift and the cleaner `security.scanned` semantics.
- [ ] **Phase 6 closed**: this PR ships the last two items
  (#5, #7) from the 2026-05 stress-test menu. 15 of 15 items
  resolved (10 fixed, 2 mitigated via RFC-0017's CSV, 3
  corrected as misdiagnoses or out-of-scope).
