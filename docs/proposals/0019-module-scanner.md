# RFC-0019: High-Performance & Accurate Module Scanner

**Status:** Implemented (PRs #1 + #2 + #3 merged; perf assertion DoD item carried forward)
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

### PR #1 — Tracer: camelCase + malformed-file handling — **MERGED**
- Dual-accessor reverse map.
- Regex update to admit camelCase tokens.
- `OSError` / `UnicodeDecodeError` per-module recovery + `MOD-001`
  finding.
- Unit + integration tests covering both forms and malformed files.
  (The dedicated 200+ module fixture is deferred to PR #3, where the
  benchmark needs it.)

### PR #2 — Bundle Attribution — **MERGED**
- Catalog-aware bundle resolution still on the sync scanner.
- `_build_bundle_accessor_map(catalog)` produces a second reverse
  lookup table keyed by ``bundles.<dotted>`` and ``bundles.<camelCase>``,
  each mapping to the bundle's full member tuple.
- Scan loop consults the bundle table only after the library table
  misses, so direct ``libs.<lib>`` references keep their fast path.
- Bundle members credited under the configuration the bundle was
  declared with (``implementation`` → ``impl`` bucket, ``api`` → ``api``
  bucket, etc.). A library referenced both directly and via a bundle in
  the same module is credited exactly once per bucket — dedup falls
  out of the existing "already in bucket" check.
- A bundle that references an alias missing from `[libraries]` no
  longer crashes; the orphan reference is silently skipped (catalog
  health rule ``HDX-002`` flags the catalog problem separately).
- 13 new unit + integration tests in
  `tests/infrastructure/scanners/test_gradle_module_scanner.py`
  covering: dotted form, camelCase form, mixed-KTS-Groovy projects,
  per-configuration attribution, dedup with direct declarations,
  ``direct_dep_count`` expansion, orphan member tolerance, unused
  bundles.

### PR #3 — Async refactor — **MERGED**
- `GradleModuleScanner.scan` is now `async def`. Per-module work
  (read + regex + classify) is extracted into a pure helper
  `_scan_module_file(...)` dispatched through `asyncio.to_thread`;
  results are awaited with `asyncio.gather`. The aggregator stays in
  the main coroutine — no shared mutable state across tasks.
- `ModuleUsageScanner` port signature changed to `async def scan(...)`,
  matching the other six async adapter ports in the project.
- `GenerateFreezeReport.execute` likewise became `async def`. The
  previous pattern of seven independent `asyncio.run(...)` calls is
  gone; a single `asyncio.run(...)` lives at the CLI entry
  (`CheckCommand.run`). This means every adapter now shares one event
  loop, one default thread pool, and (once HTTP adapters consolidate)
  one `httpx.AsyncClient` connection pool.
- Synthetic project generator under
  `tests/fixtures/large_project_generator.py` produces 1-N module
  trees with the three accessor styles (dotted / camelCase / bundle)
  and the three configuration buckets (impl / api / test). Seeds the
  PRNG for reproducibility.
- Benchmark tests under
  `tests/infrastructure/scanners/test_gradle_module_scanner_bench.py`
  run on `BENCH=1` only. They print wall-clock for 200- and
  500-module scans plus a smoke assertion that the generator exercises
  enough of the alias pool to be representative. No timing assertion
  is currently enforced — see "Carry-forward" below.

### Carry-forward — perf-assertion DoD item

The RFC originally asked for ">3x faster than the sync baseline" as
the performance gate. PR #3 ships the async pipeline but defers the
formal assertion. The three options considered (in-process serial-vs-
async ratio, committed numeric baseline, single absolute threshold)
all carried trade-offs we chose not to pay in this PR:

- The serial-vs-async helper required maintaining a parallel sync
  code path purely for benchmarking — production complexity for test
  signal.
- The committed numeric baseline tied the gate to a specific machine
  class and would have produced false positives on slower CI runners.
- The absolute threshold would have passed trivially on SSDs and
  failed on network drives, providing no real protection.

The benchmark **does** run end-to-end on demand and prints timings,
so anyone investigating a regression can compare two PRs locally
without rebuilding the harness. Picking the right gating strategy is
tracked as a follow-up to revisit once we have more datapoints from
real customer projects.

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

- [x] **Integration:** Async scanner wired in the **Composition Root**
  (`bootstrap.py`). _(PR #3 — port became async; the use case awaits
  it directly; `bootstrap.py` already returns the adapter unchanged.)_
- [x] **Architecture:** Follows ADR-0006 and the Tracer Bullet path
  from ADR-0009. _(PRs #1 + #2 + #3.)_
- [x] **Accuracy:** Unit tests verify detection of dotted, camelCase,
  and bundle accessors. _(PR #1 dotted/camelCase; PR #2 bundles.)_
- [x] **Resilience:** Malformed `build.gradle(.kts)` files produce
  `MOD-001` findings rather than crashes. _(PR #1.)_
- [ ] **Performance:** >3x faster on the 200+ module generated fixture
  compared to the sync baseline. _(PR #3 ships the async pipeline + a
  200/500-module benchmark that prints wall-clock; formal ratio
  assertion is deferred — see "Carry-forward" above.)_
- [x] **Testing:** Integration tests cover a multi-module project
  structure with mixed `.gradle` and `.kts` files, bundle declarations,
  and at least one intentionally malformed file. _(PR #1 mixed +
  malformed; PR #2 bundles + mixed-form bundles; PR #3 generator
  exercises all three at 200+ modules.)_
