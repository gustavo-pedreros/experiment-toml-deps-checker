# RFC-0025: Parallel Orchestration of Independent Adapter Stages

**Status:** Proposed
**Created:** 2026-05-17
**Related JTBDs:** JTBD-5 (report accuracy), JTBD-6 (developer experience)
**Depends on:** RFC-0019 (async scan pipeline), RFC-0024 PR #1 (async GHSA scanner)

## Problem

After RFC-0024 PR #1 cut the GHSA scan from ~50 s to single-digit
seconds, empirical measurement on a 170-library catalog with a valid
GitHub token dropped from **59 s → 12.5 s wall-clock** (cold cache,
`--module-usage --risk-score`). The fix was real and material, but
the remaining 12.5 s is dominated by a **second** structural
issue that the previous RFC's PR body misdiagnosed as
"Maven version resolution + license POM fetches are still serial".

Closer reading of `GenerateFreezeReport.execute` (`generate_freeze_report.py:100-185`)
reveals the actual shape:

```python
# Pseudo-shape — each ``await`` is fully resolved before the next starts.
bom_resolutions = await self._bom_resolver.resolve(bom_libraries)
catalog = enrich_catalog_with_boms(catalog, bom_resolutions)

findings = self._health_checker(catalog)             # sync, fast

security_advisories = await self._scanner.scan(libraries)        # ~5 s cold
# ... toolchain + compliance checks (sync, fast) ...
library_health_findings = await self._library_health_checker.check(libraries)   # ~2 s cold
changelog_entries = await self._changelog_fetcher.fetch(libraries)              # ~2 s cold
module_usage_map = await self._module_usage_scanner.scan(catalog_path, catalog) # ~0.5 s
license_audit = await self._license_checker.check(libraries)                    # ~3 s cold
library_version_statuses = await self._version_status_resolver.resolve(libraries) # ~3 s cold

# risk score consumes everything → must come last
```

**Every adapter is already internally parallel** — `MavenVersionStatusResolver`,
`PomLicenseChecker`, `ChangelogFetcher`, `GitHubAdvisoryScanner` (after
RFC-0024), `GradleModuleScanner` (after RFC-0019 PR #3), `LibraryHealthChecker`
(via its own `asyncio.gather`). The wall-clock penalty comes from the use
case **awaiting each stage in serial** at the orchestration level. Sum of
the per-stage costs ≈ 5 s + 2 s + 2 s + 0.5 s + 3 s + 3 s ≈ 15 s of
HTTP-bound work, run one stage at a time.

After this RFC the same independent stages would `asyncio.gather` together;
total wall-clock would be dominated by the **slowest single stage** plus
fixed costs (parsing, BoM resolution, risk score computation). Expected:
**~5-7 s** for the same 170-library catalog on cold cache (down from
12.5 s).

## Proposed solution

Restructure `GenerateFreezeReport.execute` into three explicit phases:

```python
async def execute(self, catalog_path: Path) -> FreezeReport:
    # Phase 0 — sequential prelude (catalog parsing + BoM enrichment).
    catalog = self._parser.parse(catalog_path)
    bom_resolutions, catalog = await self._resolve_boms_if_any(catalog)
    findings = self._health_checker(catalog) if self._health_checker else ()
    compliance_findings = self._compliance_checker.check(catalog) if ... else ()
    toolchain_findings = self._toolchain_checker.check(catalog) if ... else ()

    # Phase 1 — parallel fan-out: every adapter that consumes the
    # enriched catalog independently runs concurrently.
    libraries = tuple(catalog.libraries)
    (
        security_advisories,
        library_health_findings,
        changelog_entries,
        module_usage_map,
        license_audit,
        library_version_statuses,
    ) = await asyncio.gather(
        self._safe_scan(libraries),
        self._safe_library_health(libraries),
        self._safe_changelog(libraries),
        self._safe_module_usage(catalog_path, catalog),
        self._safe_license(libraries),
        self._safe_version_status(libraries),
    )

    # Phase 1.5 — fold scanner findings into the shared findings tuple.
    if module_usage_map is not None and module_usage_map.findings:
        findings = findings + module_usage_map.findings

    # Phase 2 — sequential consumer (risk score depends on all of Phase 1).
    risk_score_report = score_libraries(...) if self._enable_risk_score else None

    return FreezeReport(...)
```

The `_safe_*` wrappers (one per adapter) handle the "adapter is None"
case by returning the empty-result sentinel, so the `gather` call site
stays clean:

```python
async def _safe_scan(self, libraries: tuple[Library, ...]) -> tuple[LibraryAdvisory, ...]:
    if self._scanner is None:
        return ()
    return await self._scanner.scan(libraries)
```

This shape:

- **Preserves the exact set of inputs and outputs** each adapter sees.
  No port signature change, no domain model change.
- **Keeps BoM resolution in Phase 0** because every downstream adapter
  reads the enriched catalog. Running it concurrently with Phase 1
  would race against catalog enrichment.
- **Keeps risk score in Phase 2** because it consumes the output of
  every Phase 1 adapter; running it concurrently is impossible by
  data dependency.
- **Lets sync checks (compliance, toolchain, health) run in Phase 0**
  alongside parsing. They're synchronous and their cost is
  microseconds; folding them into Phase 1 would gain nothing.

### Concurrent connection-pool considerations

When all six Phase 1 adapters run concurrently, each opens its own
`httpx.AsyncClient` inside its `scan` / `fetch` / `check` /
`resolve` method. That's six independent connection pools active at
peak — well within OS file-descriptor limits (typical default 1024)
and below GitHub's recommended concurrency. No change required.

A future RFC could thread a shared client through the use case for
marginal connection-setup savings, but it's a separate concern (port
signature change, lifecycle management). Out of scope here.

## Tracer Bullet Path (ADR-0009)

The whole change is the tracer: a single use case refactor with no
new adapters, no new domain types, no new wiring. The PR is small in
LoC and the test surface is exactly the existing
`test_generate_freeze_report.py` integration tests, which already
exercise every adapter combination in fakes.

The tracer step within the PR consists of:

1. **Infrastructure**: extract the six `_safe_*` async wrappers as
   private methods on `GenerateFreezeReport`. Each is one if-check
   plus a delegation call.
2. **Composition Root**: no wiring change — adapter injection is
   unchanged.
3. **Minimal Output**: keep the existing integration test suite
   green. Add one new test that uses asyncio-friendly fake adapters
   (each `await asyncio.sleep(0.05)`) and asserts the use case
   completes in materially less than `6 * 0.05 = 0.3 s` (target ~
   0.05-0.1 s).

## Implementation Plan

### PR #1 — Single PR: parallel orchestration of Phase 1

- Refactor `GenerateFreezeReport.execute` into the three-phase shape
  described above. Wrap each Phase 1 adapter call in a `_safe_*`
  helper so the `gather` call site stays free of `is None` branches.
- All existing tests in
  `tests/application/test_generate_freeze_report.py` continue to
  pass without modification (the contract is unchanged — same
  inputs, same outputs, just less wall-clock).
- One new concurrency-proof test using asyncio-friendly fakes (each
  adapter `await asyncio.sleep(t)` for a measurable `t`), asserts
  total `execute` wall-clock is closer to `max(t)` than `sum(t)`.
  Generous slack to avoid CI flakiness.
- CHANGELOG entry under `[Unreleased] / Changed` describing the
  wall-clock improvement, with the explicit note that adapter
  contracts and output shapes are unchanged.

## Performance Validation Strategy

Measured baseline (with token, cold cache, post-RFC-0024 PR #1):

- 170-library catalog (fintech-style): **12.5 s**.
- 103-library catalog (nowinandroid): observed before RFC-0024 at
  39 s pre-fix; after PR #1 likely ~8 s (not re-measured at the time
  of writing — covered by the empirical-validation step of this RFC).

Target after PR #1:

- 170-library catalog: **< 8 s** (target ~5-6 s).
- 103-library catalog: **< 5 s** (target ~3-4 s).

The wall-clock floor is the slowest individual Phase 1 adapter, which
on cold cache is typically `_scanner.scan` (now ~3 s for 170 libs
with GHSA gather) or `_license_checker.check` (similar).

CI mitigation against flakiness: the in-tree test uses deterministic
fake adapters with explicit sleeps; the assertion compares
serial-equivalent (`sum(t)`) vs measured wall-clock (`max(t)` plus
overhead), with slack. Same "benchmark prints, does not assert
ratios" pattern from RFC-0019 PR #3 applies; formal regression gate
deferred as carry-forward.

## Alternatives considered

- **Fold sync checks (compliance, toolchain, health) into the Phase
  1 `gather`.** Rejected — they're synchronous and their cost is
  microseconds. Wrapping them in `asyncio.to_thread` adds threading
  overhead larger than the benefit. Leaving them in Phase 0 is
  simpler and faster.
- **Move BoM resolution into Phase 1, accepting that downstream
  adapters see the unenriched catalog.** Rejected — BoM enrichment
  changes which libraries appear and what versions they pin. Every
  downstream adapter would compute against a stale catalog, and
  results would not match the rendered report (which uses the
  enriched catalog). Correctness would regress.
- **Use `asyncio.TaskGroup` (Python 3.11+) instead of
  `asyncio.gather`.** Slightly cleaner exception semantics
  (cancellation cascades), but the project targets Python 3.11+
  already. Either works; `gather` is what the rest of the codebase
  uses (RFC-0019 PR #3, RFC-0024 PR #1), so consistency wins. Could
  revisit if a future RFC has a real reason.
- **Share a single `httpx.AsyncClient` across all Phase 1 adapters.**
  Marginal connection-setup savings (each client today is short-
  lived; pooling overhead is tens of milliseconds at most). Adds a
  port signature change (each adapter would receive the client at
  construction). Out of scope; revisit if profiling shows
  connection setup is a real cost.
- **Use `asyncio.Semaphore` to cap concurrent adapters (e.g.
  Semaphore(3)).** Rejected — adapters are independent, finite (six
  of them), and each already bounds its own per-library concurrency.
  Capping at the orchestration level would defeat the whole point of
  fan-out.

## Cost estimate

Small. ~50 LoC of refactor in
`src/gradle_deps_monitor/application/generate_freeze_report.py`, six
small `_safe_*` helper methods, one new concurrency-proof test in
`tests/application/test_generate_freeze_report.py`, one CHANGELOG
entry. No new dependencies. No port signature changes. No domain
model changes.

## Success metrics

- **Performance**: cold-cache run against the 170-library fintech
  corpus drops from 12.5 s to < 8 s wall-clock (target ~5-6 s).
  Captured in PR description with before/after numbers, same
  validation methodology as RFC-0024 PR #1 (delete caches, run with
  token, time).
- **Per-adapter behaviour unchanged**: every adapter sees the same
  input tuple and produces the same output tuple as before.
  Validated by the existing integration test suite passing without
  modification.
- **Concurrency proven**: the new fake-adapter test asserts
  wall-clock is materially less than `sum(t_per_adapter)`, with
  slack for CI noise.
- **No regression**: all existing tests in
  `tests/application/test_generate_freeze_report.py` pass
  unmodified.

## Schema impact

`none`. Pure orchestration refactor; every adapter contract is
unchanged. `freeze.json` shape, console summary, Markdown report —
all identical to pre-PR runs apart from wall-clock.

## Rollback strategy

Revert the single PR → use case returns to the sequential
`await`-per-stage shape; wall-clock returns to the post-RFC-0024
baseline. No schema migration. No cache invalidation. Downstream
consumers see no change in behaviour.

## PR budget

Estimated **1 PR** from tracer to DoD. The change is contained to a
single file (`generate_freeze_report.py`) plus its test file, and
the contract is unchanged so the integration test suite acts as a
free regression net.

## Definition of Done (DoD)

- [ ] **Integration**: Refactored use case wired in the **Composition
  Root** (`bootstrap.py`). No wiring change required — the use case
  is constructed identically and the adapter injection is unchanged.
- [ ] **Architecture**: Follows ADR-0006 (Clean Architecture) and
  ADR-0009 (Tracer Bullets). Concurrency pattern is `asyncio.gather`
  at the orchestration level, mirroring RFC-0024 PR #1 inside each
  adapter.
- [ ] **Performance — measured**: cold-cache scan time on a
  ≥100-library catalog with token drops from > 10 s to < 8 s.
  Captured in PR description with before/after wall-clocks.
- [ ] **Performance — protected**: concurrency-proof test in
  `test_generate_freeze_report.py` asserts `execute()` with N
  fake adapters each sleeping `t` completes in materially less than
  `N * t` (with slack for CI noise).
- [ ] **Per-adapter behaviour unchanged**: every existing test in
  `test_generate_freeze_report.py` passes unmodified; no port
  signature changes; no domain model changes.
- [ ] **Documentation**: CHANGELOG entry under `[Unreleased] /
  Changed` credits RFC-0025 and explains the wall-clock improvement
  with explicit "no contract change" note.
