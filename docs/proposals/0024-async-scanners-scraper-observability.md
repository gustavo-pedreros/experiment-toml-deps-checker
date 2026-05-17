# RFC-0024: Async Vulnerability Scanners + Changelog Scraper Observability

**Status:** Implemented (PRs #52 + #53 merged 2026-05-17)
**Created:** 2026-05-17
**Related JTBDs:** JTBD-5 (report accuracy), JTBD-6 (developer experience)
**Depends on:** RFC-0001 (CVE scan), RFC-0004 (Changelog scraping)

## Problem

Two distinct HTTP-adapter reliability issues surfaced during
cross-corpus stress testing (a ~200-module fintech-style Android
project plus Google's open-source `nowinandroid`):

### Bug A — `GitHubAdvisoryScanner` is per-library serial

The GHSA scanner iterates over the library tuple with a plain `for`
loop and `await`s each request individually:

```python
# github_advisory_scanner.py:88
async def _scan_with(self, client, libraries):
    results: list[LibraryAdvisory] = []
    for lib in libraries:
        advisories = await self._advisories_for(client, lib)
        results.append(...)
    return tuple(results)
```

Despite being `async def`, the loop awaits each `_advisories_for`
fully before starting the next. With a 200-ms median round-trip per
GHSA query, that's **~30-50 s of wall-clock time on a cold cache**
for typical Android catalogs:

- 103 libraries (nowinandroid, cold cache, with token):
  measured **39 s** wall-clock total. Module scan + Maven version
  resolution + license audit complete in single digits; the
  serial GHSA loop accounts for ~30 s of the run.
- 170 libraries (fintech corpus, cold cache, with token):
  measured **59 s** wall-clock; a warm-cache re-run drops to **9 s**.
  The 50 s delta is the same serial-scan cost made visible by
  cache misses.

This contradicts the project pattern set by RFC-0019 PR #3, where
`GradleModuleScanner` was refactored from a serial loop to
`asyncio.gather` over per-module workers. The GHSA scanner was left
as-is.

**`OssIndexScanner` is NOT affected.** Closer reading reveals it
batches uncached PURLs in groups of 128 per POST (constant
`_BATCH_SIZE` in `oss_index_scanner.py`). For 170 libraries that's
two sequential POSTs at most — total per-scanner overhead in the
hundreds of milliseconds, not tens of seconds. Parallelising those
two batches would save ~200 ms; not worth a PR. The visible serial
`for` loop at line 115 is cache lookup, not network I/O. Out of
scope for this RFC; can be revisited if catalogs grow large enough
that 8+ batches become the bottleneck.

### Bug B — Changelog scraper degrades silently under GitHub rate limit

`ChangelogFetcher` is already correctly parallel (it uses
`asyncio.gather` for both latest-version lookup and per-library entry
construction). The remaining issue is **observability**: when the
unauthenticated 60 req/h GitHub limit is exhausted (typical after
2-3 back-to-back runs against a large catalog), the fetcher's
internal HTTP calls return 403, the affected library's
`ChangelogEntry` falls back to `BreakingSignal.UNKNOWN` with a bare
repository URL (no release-tag link, no snippet), and **nothing in
the report indicates the run was degraded**.

This was observed concretely between two consecutive runs against
the fintech corpus: `pubnub 9.2.3 → 13.3.0` was correctly classified
`BREAKING` (with the full `/blob/master/CHANGELOG.md` URL and a
`v13.3.0` snippet) in run 1, and silently became `UNKNOWN` (with
`https://github.com/pubnub/kotlin` as a bare URL, no snippet) in
run 3 — same code path, same catalog, same machine, just rate
limit exhaustion in between. A user reading the second report has
no way to tell the data quality dropped.

The mitigation is well-known (set `GITHUB_TOKEN` to raise the
limit to 5 000 req/h), but the report has to surface the symptom
for a user to know they should apply it.

## Proposed solution

Two narrow changes plus a small presentation-layer addition. No new
dependencies, no schema-breaking changes.

### 1. Async refactor of `GitHubAdvisoryScanner._scan_with`

Replace the serial `for` loop with `asyncio.gather` over per-library
coroutines, guarded by an `asyncio.Semaphore` to bound concurrency
politely:

```python
# Constant near the existing _PER_PAGE / _DEFAULT_TTL:
_MAX_CONCURRENT_REQUESTS = 20

async def _scan_with(self, client, libraries):
    sem = asyncio.Semaphore(_MAX_CONCURRENT_REQUESTS)

    async def _one(lib: Library) -> LibraryAdvisory:
        async with sem:
            advisories = await self._advisories_for(client, lib)
        return LibraryAdvisory(
            alias=lib.alias,
            coordinate=f"{lib.group}:{lib.artifact}",
            version=str(lib.version),
            advisories=tuple(advisories),
        )

    return tuple(await asyncio.gather(*(_one(lib) for lib in libraries)))
```

`Semaphore(20)` keeps the request rate well within GitHub's
authenticated 5 000 req/h envelope (typical Android catalogs query
once per library; the burst is short). Without auth (60 req/h),
the rate limit is the bottleneck and no amount of concurrency helps
— but it doesn't make things *worse* either.

`OssIndexScanner` is intentionally NOT touched in this RFC — its
existing batched POST design already amortises per-library cost (see
"Bug A" above).

### 2. Rate-limit observability in `ChangelogFetcher`

Add a small statistics tracker that the fetcher updates as it
classifies each library's outcome:

```python
@dataclass(frozen=True)
class ChangelogFetchStats:
    attempted: int                # libraries with a candidate major upgrade
    fetched: int                  # got release notes body + URL
    fallback_url_only: int        # only the repo URL (no body)
    rate_limited: int             # explicitly observed HTTP 403 + rate-limit headers
    unknown_no_repo: int          # POM had no SCM URL / GitHub repo
```

`ChangelogFetcher.fetch(...)` returns a tuple
`(entries, stats)` instead of just `entries`. The presentation layer
reads `stats.rate_limited > 0` to decide whether to emit a warning:

- Console summary: a line below the Major Upgrades panel —
  `⚠️ Major Upgrades — N of M release notes fetched, K fell back
  to repo URL (GitHub rate limit — set GITHUB_TOKEN for full
  coverage)`.
- Markdown report: same line under the section header.

Detection rule: a response is "rate-limited" when the status is 403
and `X-RateLimit-Remaining` is `0` (primary limit) **or** the status
is 429 (secondary limit). Anything else (timeout, 404, plain 403
without rate headers) counts as `unknown_no_repo` or
`fallback_url_only` depending on which stage failed.

## Tracer Bullet Path (ADR-0009)

The highest-impact single change is the GHSA async refactor: 30-50 s
of wall-clock vanish on a typical cold-cache run. We make it the
tracer because:

1. It mirrors a pattern (`asyncio.gather` with bounded concurrency)
   that's already proven in `GradleModuleScanner` (RFC-0019 PR #3) —
   low novelty, easy review.
2. Output is byte-for-byte identical to the serial version (advisory
   ordering depends on the per-library API response, which is
   independent of concurrency).
3. The refactor is contained to `_scan_with`; no port signature
   change, no composition-root rewiring.

The tracer step within PR #1 consists of:

1. **Infrastructure:** introduce `_MAX_CONCURRENT_REQUESTS = 20`
   constant; refactor `_scan_with` to use the inner `_one`
   coroutine + semaphore + `asyncio.gather`.
2. **Composition Root:** no change — the scanner is already
   registered.
3. **Minimal Output:** an integration test that scans against an
   `httpx.MockTransport` with a fixed-latency response (e.g. a
   `0.05 s` sleep per call) and asserts the wall-clock for 50 libs
   is closer to `0.05 × 50 / 20 ≈ 0.13 s` than to the serial
   `0.05 × 50 = 2.5 s`. The assertion uses a slack factor (e.g.
   `< 1.0 s`) to avoid CI flakiness while still proving concurrency.

## Implementation Plan

Two PRs total. PR #1 ships the tracer (scanner perf refactor — the
most user-felt cost). PR #2 ships the observability story end-to-end
including JSON exposure.

### PR #1 — Tracer: `GitHubAdvisoryScanner` async refactor

- `_MAX_CONCURRENT_REQUESTS = 20` constant added at module level in
  `github_advisory_scanner.py`.
- `_scan_with` refactored to use an inner `_one` coroutine, a
  per-scan `asyncio.Semaphore`, and `asyncio.gather`. Output order
  matches input order (`gather` preserves submission order), so no
  consumer sees any contract change.
- All existing tests continue to pass without modification.
- One new concurrency-proof test using `httpx.MockTransport` with a
  fixed-sleep handler; asserts the parallel run is materially
  faster than the serial baseline, with generous slack to avoid CI
  flakiness.
- CHANGELOG entry under `[Unreleased] / Changed` describing the
  perf improvement.

### PR #2 — Changelog scraper observability (stats + render + JSON)

- New `ChangelogFetchStats` frozen dataclass under
  `gradle_deps_monitor.domain.changelog`.
- `ChangelogFetcher.fetch(...)` return type becomes
  `tuple[tuple[ChangelogEntry, ...], ChangelogFetchStats]`. Internal
  call sites update stats as they classify each outcome.
- Rate-limit detection: utility that inspects an `httpx.Response`
  for the rule "status is 403 with `X-RateLimit-Remaining: 0`, OR
  status is 429". Centralised so future adapters can reuse.
- Application layer: `GenerateFreezeReport` exposes the stats on
  `FreezeReport.changelog_stats` (new optional field, defaults
  to a zero-stat instance when no scraping ran).
- Console summary: when `stats.rate_limited > 0`, emit the warning
  line below the Major Upgrades panel.
- Markdown writer: same line emitted under the Major Upgrades
  section header.
- JSON writer: new `changelog_stats` object under `major_upgrades`,
  schema bumped to **MINOR** per ADR-0008 (additive optional field).
  Default zero-stat instance serialises to plain integers; consumers
  reading `1.x` tolerate the new field per ADR-0008.
- CHANGELOG entry under `[Unreleased] / Added` describing the new
  warning + JSON field.

## Performance Validation Strategy

Measured baseline (with token, cold cache):

- 103-library catalog (nowinandroid): **39 s** today.
- 170-library catalog (fintech corpus): **59 s** today.

Target after PR #1:

- Same two catalogs: **< 10 s** (target ~5 s).
- Wall-clock dominated by the slowest individual GHSA round-trip
  multiplied by `ceil(N / 20)`, plus the fixed cost of Maven
  resolution / module scan / license audit / etc.

Mitigation against CI flakiness: the in-tree benchmark uses a
`MockTransport` with a deterministic sleep; the assertion compares
serial-equivalent vs measured wall-clock, with slack. The same
"benchmark prints, does not assert ratios" pattern from
RFC-0019 PR #3 applies here. A formal regression gate is deferred
as carry-forward, same shape.

## Alternatives considered

- **Use `httpx.AsyncClient` connection-pool tuning instead of an
  application-level semaphore.** Rejected — the connection pool
  doesn't bound *queue depth*, only *open sockets*. A 200-library
  burst would still queue 200 tasks at the asyncio layer and could
  trigger GitHub's secondary abuse limits even with auth. The
  semaphore is explicit and adjustable.
- **Make the semaphore size configurable via
  `gradle-deps-monitor.toml`.** Rejected for the tracer — the
  default (20) is conservative for both authenticated and
  unauthenticated use. Configurability is easy to add later if a
  real user need surfaces.
- **Add disk cache to `ChangelogFetcher` so rate-limit hits
  matter less.** Real improvement, but distinct concern (Bug C, not
  Bug B). Out of scope here; tracked separately in the post-RFC
  bug menu.
- **Expose `ChangelogFetchStats` in `freeze.json` directly in this
  RFC.** Rejected for PR #3 to keep the schema impact at zero. The
  stats are already useful in console + markdown; JSON exposure
  becomes a one-line addition once the field is stable.
- **Detect rate limit by inspecting response body / JSON.** More
  fragile than header inspection — GitHub returns helpful HTML
  bodies sometimes, JSON others, plain text on 429. Headers
  (`X-RateLimit-Remaining`, response code) are the documented,
  stable contract.

## Cost estimate

Medium. ~30 LoC in each of the two scanners (PRs #1 + #2), ~70 LoC
across the fetcher / application / presentation layers for PR #3,
plus tests in each layer. No new dependencies. No external API
surface change.

## Success metrics

- **Performance**: scanning the validation corpus (170 libs, cold
  cache, with token) drops from ~59 s to < 10 s wall-clock total.
  Same proportional speedup expected for nowinandroid (39 s → < 8 s).
  Warm-cache re-runs are already fast and stay fast.
- **Observability — positive case**: a run that exhausts the GitHub
  rate limit (reproducible by running three times in a row without
  a token against any catalog with ≥ 15 major upgrades) shows a
  warning line in both console and Markdown output explicitly
  naming the symptom and the fix (`set GITHUB_TOKEN`).
- **Observability — negative case**: a run that completes within
  the rate-limit budget shows no warning (i.e. the warning is
  silent by default and only appears when degradation actually
  occurred).
- **No regression**: existing tests in
  `tests/infrastructure/scanners/test_github_advisory_scanner.py`,
  `test_oss_index_scanner.py`, and
  `tests/infrastructure/fetchers/test_changelog_fetcher.py` pass
  unmodified. (Note: the changelog fetcher tests carry 25
  pre-existing Python 3.14 `asyncio.get_event_loop()` failures
  documented in PRs #47/#48/#50/#51 — those remain out of scope
  for this RFC too.)

## Schema impact

- **PR #1**: `none` — pure refactor of both scanners, identical
  output.
- **PR #2**: `minor` per ADR-0008. New optional `changelog_stats`
  object added under `major_upgrades` in `freeze.json`. Consumers
  reading `1.x` MUST tolerate the new field (and this is the
  documented contract). Default values (all zeros) are emitted
  when no scraping ran, so the field is always present and never
  null.

## Rollback strategy

- Revert PR #1 → GHSA scanner returns to serial; the only
  observable change is slower wall-clock on cold cache. No schema
  migration.
- Revert PR #2 → warning lines disappear from console + Markdown;
  `changelog_stats` disappears from `freeze.json`; scraper
  continues to degrade silently as it did before. Schema bump is
  trivially reverted (additive change, no consumer is forced to
  read the new field).

Both PRs are independently revertable. If a specific change inside
a PR causes regressions, the multi-commit structure makes
`git revert <commit>` straightforward.

## PR budget

Estimated **2 PRs** from tracer to DoD. PR #1 is scoped to GHSA
alone (OSS Index's batched POST design already amortises per-library
cost — see the "Bug A" analysis). PR #2 keeps the observability
story (domain + application + presentation + JSON schema) intact in
a single PR so the warning is wired end-to-end before it ships.

## Definition of Done (DoD)

- [ ] **Integration**: Updated scanners and fetcher wired in the
  **Composition Root** (`bootstrap.py`). No new wiring required
  for PRs #1/#2; PR #3 plumbs `ChangelogFetchStats` through the
  use case.
- [ ] **Architecture**: Follows ADR-0006 (Clean Architecture) and
  ADR-0009 (Tracer Bullets). Concurrency pattern mirrors RFC-0019
  PR #3 (`asyncio.gather` + thread-safe aggregation).
- [ ] **Performance — measured**: PR #1 brings cold-cache scan time
  on a ≥100-library catalog from > 30 s to < 10 s. Captured in the
  PR description with before/after wall-clocks.
- [ ] **Performance — protected**: Concurrency-proof tests in
  `test_github_advisory_scanner.py` and `test_oss_index_scanner.py`
  assert that a `MockTransport`-driven scan with N libs and
  per-call sleep `t` completes in materially less than `N * t`
  (with slack for CI noise).
- [ ] **Observability — degraded run**: When GitHub rate-limits the
  changelog scraper, both console and Markdown show a warning line
  with the symptom and the `GITHUB_TOKEN` mitigation. Tested via
  `MockTransport` returning 403 + rate-limit headers for the
  relevant call.
- [ ] **Observability — clean run**: When no rate-limit hits occur,
  no warning is emitted. Tested via `MockTransport` returning 200
  responses.
- [ ] **No regression**: All existing tests in the three affected
  test files pass unmodified.
