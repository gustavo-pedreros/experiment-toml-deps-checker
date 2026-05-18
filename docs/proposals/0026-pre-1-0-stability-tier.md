# RFC-0026: `PRE_1_0` Stability Tier for `0.x.y` Versions

**Status:** Proposed
**Created:** 2026-05-17
**Related JTBDs:** JTBD-5 (report accuracy), JTBD-1 (informed upgrade decisions)
**Depends on:** RFC-0008 (JSON schema SemVer convention)

## Problem

`MavenVersion.stability` currently classifies any numeric-only version
string (e.g. `1.0.0`, `0.5.4`, `2.8.6`) as `Stability.STABLE`. This
hides a meaningful distinction that SemVer makes explicit:

> Major version zero (`0.y.z`) is for initial development. Anything
> **may** change at any time. The public API should not be considered
> stable.
> — semver.org §4

The 170-library fintech-style corpus contains several libraries pinned
on `0.x.y` versions (`snapper`, `shimmer`, every `accompanist_*`
library). The current report shows them as **Stability: stable** even
though their authors have explicitly declared "API may change at any
time" by staying below `1.0.0`. The signal that should reach the
reviewer — "this pin is on an unstable major and any upgrade may
break you regardless of the SemVer level you bump" — is lost.

Today's `Stability` enum:

```python
STABLE / RC / BETA / ALPHA / DEV / SNAPSHOT / UNKNOWN
```

Three downstream consumers filter on "not stable":

- `presentation/console.py:110` — outdated-counter excludes non-stable libs
- `infrastructure/writers/slack_writer.py:141 + 189` — non-stable count + list
- (implicit) every reader of the JSON `stability` field

All three treat `0.x.y` as if it were on equal footing with `1.0.0`,
`2.0.0`, or `33.0.0`.

## Proposed solution

Add a new value to the `Stability` enum:

```python
class Stability(StrEnum):
    STABLE = "stable"
    PRE_1_0 = "pre_1_0"    # new — 0.x.y numeric, no qualifier
    RC = "rc"
    BETA = "beta"
    ALPHA = "alpha"
    DEV = "dev"
    SNAPSHOT = "snapshot"
    UNKNOWN = "unknown"
```

Update the classifier so naked `0.x.y` (no `-alpha`/`-beta`/`-rc`/...
suffix) returns `PRE_1_0` instead of `STABLE`. Versions with a
qualifier suffix continue to classify by their suffix
(`0.5.0-alpha01` → `ALPHA`, unchanged) because the qualifier is the
stronger signal — the publisher told us "this is alpha".

```python
@property
def stability(self) -> Stability:
    if _SNAPSHOT.search(self.raw):
        return Stability.SNAPSHOT
    if _ALPHA.search(self.raw):
        return Stability.ALPHA
    if _BETA.search(self.raw):
        return Stability.BETA
    if _RC.search(self.raw):
        return Stability.RC
    if _DEV.search(self.raw):
        return Stability.DEV
    if _NUMERIC_ONLY.match(self.raw):
        # SemVer §4: major version 0 is "anything may change at any time".
        if self.raw.split(".", 1)[0] == "0":
            return Stability.PRE_1_0
        return Stability.STABLE
    return Stability.UNKNOWN
```

`is_stable` continues to return `True` only for `STABLE`. PRE_1_0 is
not stable by SemVer's own definition, so the existing identity check
(`self.stability is Stability.STABLE`) gives the correct answer
without modification. This means:

- Console outdated counter automatically includes PRE_1_0 libs (already
  filters on `is not Stability.STABLE`)
- Slack non-stable count automatically includes PRE_1_0 libs (already
  uses `not lib.version.is_stable`)
- JSON `stability` field serialises the new value as `"pre_1_0"`

`is_prerelease` is intentionally **not** broadened to include PRE_1_0.
Its semantics are "the publisher tagged this artifact with a
pre-release suffix" (alpha/beta/rc/dev/snapshot), and a naked `0.5.0`
release doesn't carry that tag. Mixing the two would conflate "the
publisher is shipping a pre-release artifact" with "the publisher
hasn't reached their first stable major" — useful as separate axes.

### Why a new enum value rather than a flag

Three alternatives were considered:

1. **New enum value** (chosen). Domain-correct; consumers that
   pattern-match on `Stability.STABLE` automatically pick up the
   distinction without code change; JSON consumers see a new discrete
   value.
2. **Add a boolean `is_pre_1_0` property without enum change.** Hides
   the distinction from the JSON schema and from any consumer that
   walks `stability` as a categorical. Cheaper but less honest about
   the model.
3. **Change `_NUMERIC_ONLY` regex to forbid leading `0`.** Would
   re-route `0.x.y` to `UNKNOWN`, conflating it with parse-failure
   values like `latest.release` and `+`. Loses information.

## JSON schema impact

`freeze.json` schema bumps **1.6.0 → 1.7.0** (MINOR per ADR-0008):
the `stability` field gains a new permitted enum value `pre_1_0`.
Consumers reading `1.x` continue to work; they may treat unknown
enum values as a fallthrough, but no existing value changes meaning.

## Tracer Bullet Path (ADR-0009)

Whole change is the tracer: single PR, no new files, contained to
one domain module plus the schema-version constant.

1. **Domain change**: add `PRE_1_0` to the enum, update the
   classifier branch, parametrize existing test table with the new
   cases.
2. **Schema bump**: `json_writer.py` `SCHEMA_VERSION = "1.7.0"`.
3. **No port signature changes, no adapter changes, no use-case
   changes.** Every consumer of `stability` already treats it as an
   opaque enum value or pattern-matches on `STABLE` specifically.

## Tests

Parametrize `tests/domain/test_maven_version.py` with new rows:

```python
("0.0.0", Stability.PRE_1_0),
("0.1.0", Stability.PRE_1_0),
("0.5.4", Stability.PRE_1_0),
("0.10.99", Stability.PRE_1_0),
# Suffix wins — 0.x.y with qualifier classifies by qualifier
("0.5.0-alpha01", Stability.ALPHA),
("0.1.0-rc02", Stability.RC),
("0.0.0-SNAPSHOT", Stability.SNAPSHOT),
# Existing rows continue to work — 1.x.y stays STABLE
("1.0.0", Stability.STABLE),
("10.0.0", Stability.STABLE),
```

Add one assertion on `is_stable` and `is_prerelease` behaviour for a
PRE_1_0 instance to lock in the contract documented above.

## Implementation Plan

### PR #1 — Single PR: PRE_1_0 stability tier

- Add `Stability.PRE_1_0` and the classifier branch in
  `src/gradle_deps_monitor/domain/version.py`.
- Bump `json_writer.SCHEMA_VERSION` to `"1.7.0"`.
- Parametrize `tests/domain/test_maven_version.py` with new cases.
- CHANGELOG entry under `[Unreleased] / Added` documenting the new
  enum value, the rationale (SemVer §4), and the schema bump.

No other files touched. Total: ~10 LoC of domain + ~10 LoC of
tests + CHANGELOG + schema constant.

## Validation Strategy

After merge: re-run against the validation corpus and confirm that
the previously-flagged `0.x.y` libraries (`snapper`, `shimmer`,
`accompanist_*`) now appear with `Stability: pre_1_0` in both the
Markdown report and the JSON, and that the console outdated counter
includes them.

## Alternatives considered

- **Name `PRE_RELEASE` instead of `PRE_1_0`.** Rejected — overloads
  the term that already implies alpha/beta/rc tagging in everyday
  usage; would suggest the publisher tagged the artifact, which they
  didn't.
- **Name `EXPERIMENTAL`.** Rejected — that's a project-policy label,
  not a version-string property. A library at `0.5.0` isn't
  necessarily "experimental" by its author's intent; it's just below
  its first stable major.
- **Make `is_prerelease` include PRE_1_0.** Rejected — see "Why a
  new enum value" above. Keeping the two axes separate is more
  honest.
- **Skip the enum value and just change `is_stable` to return
  `False` for `0.x.y`.** Rejected — hidden behaviour change without
  any schema or report-visible signal; the reviewer reading the
  report still sees `Stability: stable` and can't tell anything
  changed.

## Cost estimate

Tiny. Single domain file change (~10 LoC), single test file
extension (~10 LoC), one constant bump (`SCHEMA_VERSION`), one
CHANGELOG entry. No new dependencies, no adapter changes, no
use-case changes.

## Success metrics

- **Domain correctness**: `0.x.y` numeric-only versions classify as
  `PRE_1_0`, not `STABLE`. Suffix-qualified `0.x.y-*` versions
  continue to classify by suffix.
- **Schema compatibility**: existing JSON consumers continue to
  parse `freeze.json` (additive enum value, no required field
  changes).
- **Downstream propagation**: console outdated counter and Slack
  non-stable count automatically include the newly-distinguished
  libs without per-consumer code change.

## Rollback strategy

Revert the single PR → enum loses `PRE_1_0`, classifier reverts to
treating `0.x.y` as `STABLE`, schema constant reverts to `"1.6.0"`.
JSON consumers that had started to handle the new value gracefully
degrade (they see `"stable"` again).

## PR budget

Estimated **1 PR** from tracer to DoD.

## Definition of Done (DoD)

- [ ] **Integration**: New value visible in `freeze.json` and in the
  Markdown report's **Libraries** table `Stability` column.
- [ ] **Architecture**: Follows ADR-0006 (Clean Architecture) — the
  change is contained to the domain layer. Follows ADR-0008 (schema
  SemVer): MINOR bump for additive enum value.
- [ ] **Testing**: Parametrized test cases cover both PRE_1_0 and
  the unchanged STABLE / suffix-wins behaviour.
- [ ] **Documentation**: CHANGELOG entry under `[Unreleased] /
  Added` documents the new tier, the schema bump, and the SemVer
  §4 rationale.
