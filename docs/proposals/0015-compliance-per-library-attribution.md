# RFC-0015: Compliance per-library attribution

**Status:** Proposed
**Created:** 2026-05-06
**Related JTBDs:** JTBD-2 (Play Store readiness), JTBD-6 (rank by
risk)
**Depends on:** [RFC-0002](0002-play-store-compliance.md) (compliance
foundation), [RFC-0008](0008-risk-score.md) (consumer)

## Problem

[RFC-0008](0008-risk-score.md) reserves a 10-point dimension for
Play Store compliance in the composite risk score. The
implementation always returns `0` because `ComplianceFinding` has
no `alias` or `coordinate` field — the scorer cannot map a
finding to the library it concerns.

Consequences:

- The `compliance` dimension never contributes; the practical
  ceiling of the risk score is 90, not 100.
- Library-specific compliance issues (the most actionable kind —
  e.g., SafetyNet → Play Integrity migration) are visible in the
  Compliance section but invisible to the ranking.
- Reviewers ranking by risk score miss libraries that are about
  to break Play Store ingestion.

## Proposed solution

Extend the `ComplianceFinding` domain object with optional
attribution fields, update the existing checker to populate them
where applicable, and consume them in the scorer.

### Domain change

```python
@dataclass(frozen=True)
class ComplianceFinding:
    rule_id: str
    severity: ComplianceSeverity
    message: str
    detail: str = ""
    deadline: str | None = None
    migration: str | None = None
    # New fields:
    alias: str | None = None       # catalog alias when the finding
                                   # concerns a specific library
    coordinate: str | None = None  # group:artifact, mirrors `alias`
```

Both fields default to `None` so existing serialised diffs
continue to load. Catalog-level findings (e.g., `targetSdk` not
yet at 36) keep `alias=None`.

### Checker changes

`PlayStoreComplianceChecker` rules that detect library-specific
violations populate `alias` / `coordinate`. Examples:

| Rule | Today's message | Updated attribution |
|------|-----------------|---------------------|
| SafetyNet → Play Integrity | "library found" | `alias = "safetynet"` |
| Bouncy Castle deprecated module | catalog-wide | `alias = "bouncycastle-prov"` |
| `targetSdk` deadline | catalog-wide | `alias = None` (unchanged) |

### Scorer integration

`_score_compliance` becomes:

```python
def _score_compliance(
    alias: str,
    compliance_by_alias: dict[str, ComplianceFinding],
    cap: int,
) -> DimensionScore:
    finding = compliance_by_alias.get(alias)
    if finding is None:
        return DimensionScore("Compliance", 0, cap, "no findings")
    severity_to_score = {
        ComplianceSeverity.ERROR: cap,
        ComplianceSeverity.WARNING: cap // 2,
        ComplianceSeverity.INFO: 0,
    }
    score = severity_to_score.get(finding.severity, 0)
    return DimensionScore("Compliance", score, cap, finding.message)
```

Mapping is intentionally simple; calibration deferred to feedback
on real catalogs.

### Writers

- **Markdown / JSON**: compliance table gains a "Library" column.
  Empty cell for catalog-level findings.
- **Slack**: per-library findings show alias next to the rule
  badge.
- Schema bump: `1.x.0` → `1.x+1.0` per
  [ADR-0008](../adr/0008-json-schema-semver.md) (additive — new
  optional fields).

## Alternatives considered

- **Drop the compliance dimension and renormalise weights to
  100**: rejected. Erodes trust in the score because RFC-0008
  documented this dimension explicitly, and Play Store deadlines
  are exactly the kind of risk this tool is supposed to surface.
- **String-match the finding `message` for library names in the
  scorer**: rejected. Implicit, fragile, and breaks across
  message i18n.
- **Expand `Finding` (catalog health) to share the same type as
  `ComplianceFinding`**: rejected. Different domains; a single
  god-finding muddies semantics. (See
  [RFC-0016](0016-unified-report-style.md) for visual unification
  without merging types.)

## Cost estimate

~1 day:

- Domain field addition (backwards compatible)
- Update existing compliance rules to populate alias when
  applicable
- Scorer change + tests
- Writer column updates
- Snapshot tests for both attributed and unattributed findings

## Success metrics

- A real catalog containing SafetyNet shows the library in the
  risk score top-N with a non-zero compliance contribution.
- Catalog-level compliance findings (no alias) still render
  correctly in all writers.
- `_score_compliance` test coverage matches the other dimensions
  (no-finding, severity bands, edge cases).
