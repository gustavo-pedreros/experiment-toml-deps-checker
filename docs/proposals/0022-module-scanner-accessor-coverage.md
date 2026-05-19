# RFC-0022: Module Scanner — Accessor Coverage Follow-up

**Status:** Implemented
**Created:** 2026-05-15
**Shipped:** 2026-05-15 (PR #50)
**Related JTBDs:** JTBD-3 (blast radius), JTBD-5 (report accuracy)
**Depends on:** RFC-0019 (Module Scanner)

## Problem

Real-world stress test against a fintech-style multi-module Android
project (~200 modules, ~170 libraries, 6 bundles, 2 BoMs) surfaced two
systematic blind spots in `GradleModuleScanner` that survived the
RFC-0019 overhaul:

### Bug A — Underscore-only aliases never match dotted accessors

Catalog aliases that use **only `_` as separator** (e.g.
`internal_sdk_android`, `partner_payments_sdk`, `auth_jwt_validator`)
are silently under-counted. Gradle's catalog accessor convention
treats `-`, `_`, and `.` as **equivalent separators** — alias
`internal_sdk_android` is addressable as `libs.internal.sdk.android`
in build files. Our scanner normalises `-` → `.` but leaves `_`
untouched:

```python
def _alias_to_accessor(alias: str) -> str:
    return alias.replace("-", ".").lower()
```

Result: the lookup table contains
`"internal_sdk_android" → "internal_sdk_android"` but the regex
captures `"internal.sdk.android"` from the build file. Lookup fails,
the reference is silently dropped.

In the validation corpus, **6 underscore-only aliases** belonging to
an in-house authentication SDK cluster are referenced exclusively as
dotted accessors in a security-critical authentication module's
`build.gradle`, all under `api(...)`. None are credited. Because two
of those libraries (`auth_jwt_validator`, `auth_http_client`) carry
**HIGH-severity CVEs** for the pinned versions, the risk score
reports their `Blast radius` dimension as `0/15 "not used"` —
actively misleading: they are used, in a security-critical module,
and propagate transitively as `api`.

### Bug B — `platform(libs.x.bom)` declarations never matched

Maven BoMs are conventionally applied via the `platform()` wrapper:

```groovy
implementation platform(libs.compose.bom)
implementation platform(libs.firebase.bom)
```

The scanner regex requires `libs.` to come **directly after** the
configuration keyword and an optional opening paren:

```python
_DEP_RE = re.compile(
    r"(?:^|[(\s,])"
    r"(implementation|api|...)"
    r"\s*\(?\s*libs\.([a-zA-Z0-9_.]+)",
    ...
)
```

With `platform(` interposed between `implementation` and `libs.`, the
regex doesn't match. Result: every BoM reference is invisible. In the
validation corpus, both ecosystem BoMs (`compose_bom`, `firebase_bom`)
and a project-specific BoM show `0` direct uses despite being applied
via `platform(libs.x.bom)` in multiple modules. This breaks the
"identify high-leverage upgrades" workflow — a BoM bump is a
high-blast-radius decision and the scanner should surface it.

### Doc rot — the markdown banner under-states current capability

`markdown_writer.py:402` still claims:

> Static analysis of `build.gradle(.kts)` files. Only the
> dotted-accessor form (`libs.foo.bar`) is matched.

This was true at the RFC-0019 tracer; it stopped being true after
RFC-0019 PR #1 (camelCase) and PR #2 (bundles), and is even further
from reality once Bugs A and B are fixed. A reader who doubts a
particular count may reach for the banner to confirm the matching
contract — and walk away with the wrong mental model.

## Proposed solution

Two narrow changes, plus the banner correction. Both are pure
regex / lookup-table patches in `gradle_module_scanner.py`; no async,
no new I/O, no schema change.

### 1. Treat `_` as a separator in alias normalisation

Update `_alias_to_accessor` and `_alias_to_camel` to recognise both
`-` and `_` as separators, mirroring Gradle's convention:

```python
_SEPARATORS_RE = re.compile(r"[-_]")

def _alias_to_accessor(alias: str) -> str:
    return _SEPARATORS_RE.sub(".", alias).lower()

def _alias_to_camel(alias: str) -> str:
    parts = [p for p in _SEPARATORS_RE.split(alias) if p]
    if not parts:
        return alias
    head = parts[0].lower()
    tail = "".join(p[:1].upper() + p[1:].lower() for p in parts[1:])
    return head + tail
```

This change is symmetric for bundle aliases via the existing
`_build_bundle_accessor_map`, which already calls both helpers.

### 2. Recognise `platform(libs.x.bom)` and similar wrappers

Extend `_DEP_RE` to admit a single optional wrapper between the
configuration and `libs.`. The wrapper set covers Gradle's three BoM
application functions:

- `platform(...)`
- `enforcedPlatform(...)`
- `testFixtures(...)` (also frequently used as a wrapper around `libs.`)

```python
_DEP_RE = re.compile(
    r"(?:^|[(\s,])"
    r"(implementation|api|testImplementation|androidTestImplementation"
    r"|testRuntimeOnly|testCompileOnly|debugImplementation|releaseImplementation"
    r"|compileOnly|runtimeOnly|ksp|kapt|annotationProcessor)"
    r"\s*\(?\s*"
    r"(?:platform|enforcedPlatform|testFixtures)?\s*\(?\s*"  # optional wrapper
    r"libs\.([a-zA-Z0-9_.]+)",
    re.MULTILINE,
)
```

A library wrapped in `platform(...)` is credited under the same
configuration bucket as the outer keyword (`implementation` →
`impl`), matching the existing classification rules. No new bucket
or finding type is introduced.

### 3. Banner rewrite

Replace `markdown_writer.py:402` with a banner that reflects the
current matcher contract:

```
> Static analysis of `build.gradle(.kts)` files. Recognises every
> Gradle catalog accessor form: dotted (`libs.foo.bar`), camelCase
> (`libs.fooBar`), bundle expansion (`libs.bundles.<name>`), and
> BoM wrappers (`platform(libs.x.bom)`, `enforcedPlatform(...)`).
```

## Tracer Bullet Path (ADR-0009)

Both bug fixes plus the banner refresh ship in a single PR — each
individual change is small enough (regex/lookup-table patches and a
one-line string) that splitting them adds ceremony without lowering
risk. The underscore normalisation acts as the conceptual tracer:
it's the highest-impact, lowest-risk change of the three, and lands
first in the PR's commit history.

In the validation corpus the underscore fix alone unblocks **two
HIGH-severity CVE libraries** (an authentication JWT validator and
an HTTP client) whose risk-score blast radius is currently
underreported as zero — making it the natural first commit.

The tracer step within the PR consists of:

1. **Infrastructure:** swap the two helper functions to the
   `_SEPARATORS_RE`-based implementations. Both helpers are pure
   functions with existing unit-test coverage that pins the dotted
   contract — keep those tests, add new ones for the underscore
   contract.
2. **Composition Root:** no wiring change — the scanner is already
   registered in `bootstrap.py`.
3. **Minimal Output:** add a fixture under `tests/fixtures/` whose
   catalog declares an underscore-only alias (e.g.
   `legacy_sdk_token = { module = "com.example:legacy-sdk" }`) and
   whose build file references it as `libs.legacy.sdk.token`. Assert
   that the library usage count is `1` after a scan that previously
   returned `0`.

*This validates that the lookup table can carry richer normalisation
without breaking the existing dotted-from-`-` contract. The
`platform()` regex change and banner refresh follow in the same PR
once the tracer step passes.*

## Implementation Plan

### PR #1 — Underscore + `platform()` + banner refresh

Single PR. Commit order inside it mirrors the tracer-then-enrichment
ordering so a reviewer can read the diff incrementally.

**Step 1 — Underscore normalisation (the tracer)**

- `_alias_to_accessor` and `_alias_to_camel` rewritten to use
  `_SEPARATORS_RE = re.compile(r"[-_]")` for both `replace`-style
  flattening and `split`-style segmentation.
- New unit tests covering the four input shapes:
  - `internal_sdk_android` → `"internal.sdk.android"` and
    `"internalSdkAndroid"`
  - `androidx-core-ktx` → `"androidx.core.ktx"` and `"androidxCoreKtx"`
    *(pin existing behaviour)*
  - `compose_ui-graphics` (mixed) → `"compose.ui.graphics"` and
    `"composeUiGraphics"`
  - `retrofit` (no separators) → `"retrofit"` and `"retrofit"`
- New integration fixture with at least one underscore-only alias and
  three references in build files (`.gradle` Groovy + `.kts` dotted +
  `.kts` camelCase).
- Bundle accessor map regression test: a bundle aliased
  `legacy_sdk_bundle` containing underscore-only members should
  expand correctly when referenced as `libs.bundles.legacy.sdk.bundle`.

**Step 2 — `platform()` wrapper detection**

- `_DEP_RE` admits an optional `platform | enforcedPlatform |
  testFixtures` wrapper.
- Two new test cases per wrapper covering Groovy and KTS forms:
  - `implementation platform(libs.compose.bom)` (Groovy)
  - `implementation(platform(libs.firebase.bom))` (KTS)

**Step 3 — Banner refresh + housekeeping**

- Markdown writer banner (`markdown_writer.py:402`) replaced with the
  four-form description from §3 above; corresponding snapshot test
  (if present) updated.
- CHANGELOG entry under `[Unreleased]` describing both bug fixes
  together with the credit chain to RFC-0022.

## Performance Validation Strategy

No new performance characteristics are introduced — the regex change
adds one optional alternation group and the helper functions retain
their `O(len(alias))` cost. The 200-/500-module benchmark from
RFC-0019 PR #3 (`tests/.../test_gradle_module_scanner_bench.py`)
should report no statistically significant delta. We assert that
explicitly in PR #2 by re-running the existing benchmark and
recording wall-clocks in the PR description.

## Alternatives considered

- **Two-pass scan (one for direct, one for `platform()` wrappers):**
  Rejected. Doubles file I/O when a single regex with optional group
  costs nothing measurable.
- **Catalog-side normalisation in `TomlCatalogParser`:** Rejected.
  Would change the alias surface area for every downstream consumer
  (the JSON `alias` field, every checker, the diff machinery).
  Confining the change to the scanner keeps it a pure module-usage
  fix.
- **Drop underscores from accessor matching entirely (force kebab):**
  Rejected. We don't own the catalog convention — projects in the
  wild use underscore-only aliases freely (the validation corpus has
  7+). Forcing them to migrate is a hostile-to-users default.
- **Generalised wrapper handler (any function call between config and
  `libs.`):** Rejected. Too permissive — would match `someProject(libs.foo)`
  and credit it as a usage. Whitelisting the three known Gradle
  wrappers keeps false positives at zero.

## Cost estimate

Small. Two regex/helper changes in a single file
(`gradle_module_scanner.py`), one banner string in
`markdown_writer.py`, ~10 new unit tests, one new fixture. No new
dependencies. No external APIs touched. No schema migration.

## Success metrics

- **Underscore aliases:** in the validation corpus, the 6
  underscore-only aliases of the in-house auth cluster each report a
  non-zero `direct` count after the fix. The highest-CVE-severity
  library in that cluster sees its risk-score `Blast radius`
  dimension rise from `0/15 "not used"` to a positive value
  reflecting actual use.
- **`platform()` BoMs:** `compose_bom`, `firebase_bom`, and any
  project-specific BoMs each report a non-zero `direct` count when at
  least one module declares them via `platform(libs.x.bom)`.
- **No regression:** every existing test in
  `tests/infrastructure/scanners/test_gradle_module_scanner.py`
  continues to pass without modification (apart from the banner
  snapshot, if any).

## Schema impact

`none`. The change is purely in *which* libraries get credited; the
`module_usage_map` structure in `freeze.json` is unchanged. Existing
consumers reading `1.x` will simply observe higher counts on some
aliases.

## Rollback strategy

Revert the single PR → scanner returns to the pre-RFC-0022 state:
underscore-only aliases drop their counts back to zero,
`platform(libs.x.bom)` declarations become invisible again, banner
reverts to the dotted-only wording.

No cache invalidation is required (the scanner has no on-disk cache).
No JSON schema changes, so downstream consumers see only a count
delta on a fresh run.

If only one of the three steps causes a regression in practice, the
three-commit structure inside the PR makes a partial revert
straightforward via `git revert <commit>`.

## PR budget

Estimated **1 PR** from tracer to DoD. Both fixes are small
regex/lookup changes; bundling them with the banner refresh keeps
the diff focused and lets the reviewer trace tracer → enrichment →
housekeeping in three commits within a single PR.

## Definition of Done (DoD)

- [x] **Integration:** Updated scanner wired in the **Composition
  Root** (`bootstrap.py`). _(No wiring change required; verify the
  use case still receives an instance.)_
- [x] **Architecture:** Follows ADR-0006 (Clean Architecture) and
  ADR-0009 (Tracer Bullets).
- [x] **Accuracy — underscore:** Unit tests verify
  `_alias_to_accessor` and `_alias_to_camel` correctly normalise
  underscore-only, dash-only, and mixed aliases.
- [x] **Accuracy — `platform()`:** Unit tests verify detection of
  `platform()`, `enforcedPlatform()`, and `testFixtures()` wrappers
  in both Groovy and KTS forms.
- [x] **Integration corpus:** Fixture under `tests/fixtures/`
  exercises both fixes and asserts non-zero counts where the previous
  scanner returned zero.
- [x] **No regression:** All existing tests in
  `tests/infrastructure/scanners/test_gradle_module_scanner.py` pass
  unmodified.
- [x] **Documentation:** Markdown writer banner rewritten to
  enumerate all four accessor forms; CHANGELOG entry credits
  RFC-0022.
