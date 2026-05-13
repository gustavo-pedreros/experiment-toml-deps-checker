# RFC-0019: High-Performance & Accurate Module Scanner

**Status:** Draft
**Created:** 2026-05-07
**Related JTBDs:** JTBD-3 (blast radius), JTBD-5 (report accuracy)
**Depends on:** none

## Problem

The current `GradleModuleScanner` (RFC-0007) is a synchronous, regex-based
tool with three limitations discovered in large multi-module projects
(>100 modules):

1. **Inaccuracy (camelCase):** It only detects `libs.foo.bar` (dotted form)
   and misses `libs.fooBar` (camelCase), which is the standard generated
   accessor in KTS type-safe blocks. The scanner's own docstring
   acknowledges this. On Kotlin-DSL-heavy projects this means usage counts
   are systematically under-reported.
2. **Inaccuracy (Bundles):** Usage of `libs.bundles.myBundle` is ignored
   or misattributed. The individual libraries that compose the bundle
   never receive credit.
3. **Performance:** Reading hundreds of `build.gradle(.kts)` files
   sequentially is a bottleneck on network drives and slow CI agents.

These three problems compound: a project that uses bundles in KTS is
almost entirely invisible to the current scanner.

## Proposed solution

Overhaul `GradleModuleScanner` in three independently-shippable steps,
ordered by user-visible impact, **smallest change first**. Each step
preserves the "zero-Gradle-daemon" constraint.

### 1. Dual-Accessor Mapping (camelCase)

The internal reverse lookup map stores both forms of every library alias:

- Alias `androidx-core-ktx` matches `libs.androidx.core.ktx` **and**
  `libs.androidxCoreKtx`.

This is a regex/lookup change only — no async, no new I/O pattern, no
dependency changes. Maximum behaviour delta per line of code.

### 2. Bundle Attribution

The scanner becomes catalog-aware for bundles. When `libs.bundles.<name>`
is matched in a build file:

1. Look up the bundle in the parsed `Catalog`.
2. Increment usage for **all** libraries listed in that bundle.

Still synchronous; risk is purely about catalog access and attribution
correctness.

### 3. Async Parallel I/O

Refactor the scan loop to read and regex-parse build files concurrently
using `asyncio.to_thread` (not `aiofiles` — keeps the dependency
footprint clean and reuses stdlib semantics already used elsewhere in
the project's adapters). For 200+ modules this is expected to hide
most of the I/O latency.

### 4. Malformed-file resilience (cross-cutting)

Independent of the three steps above, the scanner must survive a
single corrupt/unreadable file:

- Catch `OSError` and `UnicodeDecodeError` per module.
- Emit a `MOD-001` finding ("Could not read build file for module `<path>`:
  <reason>") via the existing findings channel.
- Continue scanning the remaining modules.

This is folded into PR #1 because the camelCase change forces us to
touch the read path anyway.

## Performance Validation Strategy

The DoD requires >3× speed-up on a 200+ module project. To verify this
without depending on a private repository:

- **Mock Large Project Generator** lives under `tests/fixtures/` so it
  is reproducible and committed. PR #1 introduces it at 10 modules
  (enough to exercise camelCase + bundle paths); PR #3 expands it to
  200+ modules and adds the benchmark assertion.
- **Baseline / Async measurement:** wall-clock time of `scan()` on the
  generated tree, captured by a `pytest` benchmark marker (skipped by
  default, run in a dedicated CI job).
- **Local validation:** developers are encouraged to point the
  benchmark at their own multi-module repos to verify real-world gains.

## Tracer Bullet Path (ADR-0009)

The single highest-impact, lowest-risk improvement is camelCase
recognition. We make that the tracer.

The tracer PR (PR #1) consists of:

1. **Infrastructure:** extend the reverse lookup map in
   `GradleModuleScanner` to populate both dotted and camelCase entries
   from each alias; touch the existing regex to admit the camelCase
   accessor.
2. **Composition Root:** no wiring change required — the scanner is
   already registered in `bootstrap.py`. Verified via the existing
   integration test on a KTS fixture.
3. **Minimal Output:** add a KTS fixture under `tests/fixtures/` whose
   only dependency uses the camelCase form, and assert that the library
   usage count is `1` after a scan that previously returned `0`.
4. **Resilience baseline:** include the `OSError` / `UnicodeDecodeError`
   handler so the malformed-file behaviour is in place from day one.

*This validates that the regex + reverse-lookup path can carry richer
matching logic without breaking the existing dotted-form contract.*

## Implementation Plan

### PR #1 — Tracer: camelCase + malformed-file handling
- Dual-accessor reverse map.
- Regex update to admit camelCase tokens.
- `OSError` / `UnicodeDecodeError` per-module recovery + `MOD-001`
  finding.
- 10-module fixture under `tests/fixtures/` exercising both forms.
- Unit + integration tests.

### PR #2 — Bundle Attribution
- Catalog-aware bundle resolution still on the sync scanner.
- Fixture extended with `libs.bundles.<name>` usage.
- Tests verify that each library inside a bundle gets credited exactly
  once per module that uses the bundle.

### PR #3 — Async refactor
- Replace the synchronous loop with `asyncio.to_thread` for file reads;
  preserve all behaviour from PR #1 and PR #2.
- Expand the fixture generator to 200+ modules.
- Add a benchmark assertion (>3× wall-clock speed-up vs the sync
  baseline captured on the same generator).

### Optional Spike (before PR #3)
- **Spike:** compare `asyncio.to_thread` vs `aiofiles` for many small
  files across macOS / Linux / Windows. Document the chosen pattern and
  why. (Default plan is `to_thread`; spike is only run if PR #3 misses
  the 3× target.)
- **Spike:** document Gradle's exact camelCase conversion rules (digits,
  consecutive hyphens) — captured during PR #1 if any edge case shows up
  while writing tests.

## Alternatives considered

- **Full AST parsing of build files:** Rejected (too heavy; would
  require a Kotlin/Groovy parser).
- **Thread pool instead of `asyncio`:** Rejected for inconsistency with
  the existing network adapters, which all speak `asyncio`.
- **Async first, accuracy later:** Rejected. The accuracy bugs are the
  user-visible pain; async is an internal optimization. Inverting the
  order would leave the bugs in production for longer.

## Success metrics

- **Accuracy:** 100 % detection of `libs.bundles` usage and camelCase
  accessors in standard declarations.
- **Stability:** zero crashes when encountering malformed
  `build.gradle(.kts)` files; affected modules surface as `MOD-001`
  findings.
- **Speed:** >3× faster on the 200+ module generated fixture vs the
  sync baseline.

## Schema impact

`patch` — adds a new finding code (`MOD-001`) to the existing findings
stream. No structural change to `freeze.json`.

## Rollback strategy

Each PR is independently revertable:

- Revert PR #3 → scanner returns to sync; accuracy improvements stay.
- Revert PR #2 → bundle libraries lose attribution again; camelCase
  fix stays.
- Revert PR #1 → return to status quo (only dotted-form recognised).

`MOD-001` findings disappear cleanly on revert; no schema migration
required.

## PR budget

Estimated **3 PRs** from tracer to DoD (camelCase → bundles → async).
A 4th optional PR may follow if the cross-platform I/O spike justifies
swapping `asyncio.to_thread` for `aiofiles`.

## Definition of Done (DoD)

- [ ] **Integration:** Async scanner wired in the **Composition Root**
  (`bootstrap.py`).
- [ ] **Architecture:** Follows ADR-0006 and the Tracer Bullet path
  from ADR-0009.
- [ ] **Accuracy:** Unit tests verify detection of dotted, camelCase,
  and bundle accessors.
- [ ] **Resilience:** Malformed `build.gradle(.kts)` files produce
  `MOD-001` findings rather than crashes.
- [ ] **Performance:** >3× faster on the 200+ module generated fixture
  compared to the sync baseline.
- [ ] **Testing:** Integration tests cover a multi-module project
  structure with mixed `.gradle` and `.kts` files, bundle declarations,
  and at least one intentionally malformed file.
