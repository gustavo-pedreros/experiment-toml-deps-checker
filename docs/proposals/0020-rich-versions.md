# RFC-0020: Robust Version Detection (Rich Versions Support)

**Status:** Draft
**Created:** 2026-05-07
**Related JTBDs:** JTBD-5 (report accuracy), JTBD-2 (no false negatives on toolchain)
**Depends on:** none

## Problem

Gradle Version Catalogs support "rich versions": TOML tables with `strictly`,
`require`, `prefer`, and/or `reject` keys. The current parser only accepts
either a string literal or a table containing a `ref` pointing to `[versions]`.

Auditing `src/gradle_deps_monitor/infrastructure/parsing/toml_catalog_parser.py:154-184`
shows that `_resolve_version` **raises `CatalogParseError`** as soon as it
encounters a version table without a `ref` key:

```python
if isinstance(version_field, dict):
    ref = version_field.get("ref")
    if not isinstance(ref, str):
        raise CatalogParseError(f"{section} '{alias}': version table has no 'ref' key")
```

So today's behaviour is not "silently ignored libraries" — it is a **hard
crash of the whole `check` run** the first time a catalog uses
`{ strictly = "1.2.3" }` or `{ reject = ["1.0.0"] }`. For teams pinning
toolchains via `strictly` (a common pattern with Kotlin / KSP / AGP) this
makes the tool unusable.

Secondary effects once the parser is fixed:

1. **Duplicated logic risk:** without a normalized representation,
   each checker would re-parse the TOML to discover whether a library
   was pinned with `strictly`.
2. **Loss of signal:** `reject` lists are a strong correctness signal
   (the team has explicitly forbidden some versions) and deserve their
   own surface in reports.

## Proposed solution

Centralize version extraction in the parser and upgrade the domain
to model rich version metadata as a first-class value object.

### 1. Domain: `RichVersion` value object

Introduce an immutable, total value object that captures the four
rich-version keys plus the resolved "effective version":

```python
@dataclass(frozen=True)
class RichVersion:
    strictly: str | None = None
    require: str | None = None
    prefer: str | None = None
    reject: tuple[str, ...] = ()
    effective: MavenVersion  # resolved per precedence rules below
```

`MavenVersion` keeps its current semantics; `RichVersion` is what
`Library.version` exposes when the catalog uses a rich block. For plain
string versions, the parser still builds a `RichVersion` with
`require=<value>` and `effective=MavenVersion(<value>)`, so downstream
checkers see a single shape.

### 2. Parser: precedence and normalization

Update `_resolve_version` in `TomlCatalogParser` to recognize rich
version tables and produce a `RichVersion`. Precedence for the
`effective` field is:

1. `strictly` — strongest, behaves as an exact pin
2. `require` — declared baseline
3. `prefer` — soft preference
4. `reject`-only → no effective version (see edge case below)

If multiple of `strictly`/`require`/`prefer` are present, the higher-priority
one wins for `effective`, but **all** raw values are preserved on the
value object so checkers can warn (e.g. "library uses `strictly` AND
`prefer`, which is contradictory").

### 3. Edge case: `reject`-only libraries

A catalog entry of `{ reject = ["1.0.0", "1.0.1"] }` declares versions
to avoid but no positive pin. In that case:

- `effective` is `MavenVersion("")` (same sentinel currently used for
  BoM-managed entries).
- The library is **excluded from drift analysis** (we have no baseline
  to compare against).
- The library **still participates** in compliance, licensing, and
  bundle/module-usage scanning.
- The `reject` list is rendered in the report as an "Active rejections"
  hint, so the team has visibility of an intentional negative pin.

This is a behaviour decision worth flagging in the PR: today the same
sentinel means "BoM-managed", and we'll be overloading it. An alternative
is to introduce `EffectiveVersion = Pinned(MavenVersion) | BomManaged | RejectOnly`,
deferred to a follow-up if the sentinel proves ambiguous in practice.

### 4. Checker contract

Checkers stop doing any TOML-aware introspection. They consume
`Library.version: RichVersion` and use:

- `version.effective` for drift / compatibility comparisons.
- `version.strictly` to detect hard pins (e.g. `ToolchainCompatibilityChecker`
  treating `strictly` as an authoritative declaration).
- `version.reject` to surface negative pins in compliance reports.

## Tracer Bullet Path (ADR-0009)

The risk being de-risked is the **parser → domain → writer pipeline
not crashing on rich versions**. The first PR will:

1. **Infrastructure:** extend `TomlCatalogParser._resolve_version` to
   parse a single `strictly` block and build a `RichVersion`. Keep the
   existing string + `ref` paths working unchanged.
2. **Domain:** change `Library.version` from `MavenVersion` to `RichVersion`
   and provide a `.effective` shortcut so existing call sites need
   minimal edits.
3. **Composition Root:** no wiring changes; verify a unit test runs the
   default bootstrap path against a catalog that uses `strictly`.
4. **Minimal Output:** assert `freeze.json` serializes the library with
   the correct effective version and an empty `reject` list, and that
   `check` does **not** raise `CatalogParseError`.

*This validates that the "Parser → Domain → Writer" path handles
non-string versions end-to-end without crashing.*

### Tracer fixture

Use a production-style fixture (e.g. Kotlin pinned with `strictly`,
KSP following), not a synthetic minimal TOML. That way the tracer
doubles as a regression test for the customer-facing crash.

## Implementation Plan

### Phase 1: Tracer Bullet
- Parser handles `strictly` blocks.
- `Library.version` becomes `RichVersion`; call sites updated to use `.effective`.
- Fixture-based test confirms `check` runs without crashing.

### Phase 2: Exploration (Optional Spike)
- **Spike:** confirm Gradle's exact behaviour when multiple rich keys
  collide (e.g. `strictly` + `prefer`); document the rule and match it.
- **Spike:** sample popular Android libraries to find real-world `reject`
  patterns that deserve a dedicated "Active rejections" report section.

### Phase 3: Checker Migration
- `PlayStoreComplianceChecker` and `ToolchainCompatibilityChecker` consume
  `RichVersion` directly; remove any ad-hoc TOML re-parsing.
- Surface `reject` lists in the compliance report.
- Add the contradiction warning (`strictly` + `prefer` etc.).

## Alternatives considered

- **String-only support (status quo):** Rejected. Causes hard crashes
  on common toolchain catalogs.
- **Lazy fix in `_resolve_version` (return empty `MavenVersion` on
  unknown table):** Rejected. Hides the rich metadata from checkers
  and would still leave `reject` invisible.
- **Sum type `EffectiveVersion`:** Deferred. Reasonable but adds churn;
  re-evaluate if the `""` sentinel proves ambiguous after Phase 3.

## Success metrics

- The tool never crashes on a real-world catalog using `strictly`,
  `require`, `prefer`, or `reject`.
- Toolchain compatibility checks treat `strictly` as authoritative.
- `reject` lists are visible in the report.

## Schema impact

`minor` — `freeze.json` gains optional rich-version fields per library
(`strictly`, `require`, `prefer`, `reject`). Existing consumers that
only read the resolved version string continue to work; the bump is
additive per ADR-0008.

## Rollback strategy

The parser change is gated behind the new `RichVersion` type, but the
serialization is additive. If we need to roll back:

1. Revert `Library.version` to `MavenVersion` and the parser change in
   one commit — checkers that already migrated will need to switch back
   to `.effective` semantics restored as direct `MavenVersion`.
2. `freeze.json` consumers that started reading the new fields fall
   back gracefully since the fields are optional.

The pre-RFC behaviour was a crash, so "rollback" in practice means
"crash again on the same inputs"; we should only roll back if the
new path introduces a worse failure mode.

## PR budget

Estimated **3 PRs** from tracer to DoD:

1. Tracer (parser + domain + fixture test).
2. Checker migration + reject surfacing.
3. Optional warning for contradictory rich-version combinations.

## Definition of Done (DoD)

- [ ] **Integration:** Parser changes are active in the **Composition Root**.
- [ ] **Architecture:** Follows ADR-0006 and ADR-0009.
- [ ] **Accuracy:** Rich version keys are correctly prioritized
  (`strictly` > `require` > `prefer`).
- [ ] **Robustness:** No silent failures and no crashes when encountering
  `reject`-only blocks or unknown rich-version combinations.
- [ ] **Visibility:** `reject` lists appear in the compliance report.
- [ ] **Testing:** Unit tests cover all 4 rich-version keys, their
  combinations, `version.ref` interplay, and a real-fixture regression
  test for the original crash.
