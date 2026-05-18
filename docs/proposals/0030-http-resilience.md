# RFC-0030: HTTP Resilience — Shared Transport with Retry, Backoff, Rate-Limit Awareness

**Status:** Proposed
**Created:** 2026-05-18
**Related JTBDs:** JTBD-3 (reproducible runs), JTBD-1 (informed decisions)
**Depends on:** ADR-0006 (clean architecture), RFC-0024 (async scanners observability)

## Problem

The six outbound HTTP adapters (`MavenMetadataRegistry` subclasses ×2,
`GitHubAdvisoryScanner`, `OssIndexScanner`, `ChangelogFetcher`,
`PomLicenseChecker`, `LibraryHealthChecker`) each duplicate or *omit* the
same operational concerns. The audit registered four concrete risks:

- **R3 — Asymmetric concurrency caps.** `GitHubAdvisoryScanner:105` uses
  `asyncio.Semaphore(_MAX_CONCURRENT_REQUESTS)` correctly. `OssIndexScanner`
  has no Semaphore, only a batch-size cap. `ChangelogFetcher:304,319` runs
  raw `asyncio.gather` over per-library tasks with no concurrency bound.
  On a 170-library cold-cache run, OSS Index opens 170 simultaneous
  connections, which trips Sonatype's secondary abuse limits in practice.
- **R4 — No retry layer, no backoff, no `Retry-After` honoring.** Every
  adapter fails fast on the first 5xx, 429, or `httpx.RequestError`.
  `ChangelogFetcher` swallows the failure and returns `BreakingSignal.UNKNOWN`
  silently; the scanners raise `VulnerabilityScanError` and abort the
  entire batch. A single transient network blip blows up an otherwise
  green run.
- **R5 — Timeouts ad-hoc.** Maven registries use `httpx.Timeout(10.0)`;
  license / library-health / changelog use `15.0`; scanners use `30.0`.
  No central source of truth, no documented rationale.
- **R6 — Connection pool churn.** `ChangelogFetcher` opens a fresh
  `httpx.AsyncClient` per `_build_entry` call (one per library, line ~300).
  When `GenerateFreezeReport` runs all adapters in parallel via
  `asyncio.gather` (RFC-0025), the changelog fetcher is by far the largest
  source of connection setup overhead.

Rate-limit detection already exists in the codebase but only in one
place: `changelog_fetcher.py:77-94` defines `_is_rate_limited` (429 OR
`403 + X-RateLimit-Remaining: 0`). The scanners are deaf to it. The
*abstraction* is right; the *placement* is wrong.

## Goals

1. One **shared HTTP-layer module** that owns retry policy, backoff,
   rate-limit detection, timeout configuration, and concurrency capping.
2. Adopters opt in by replacing their `httpx.AsyncClient` construction
   with a factory call — no per-adapter retry logic, no duplicated
   constants.
3. The shape is a `httpx.AsyncBaseTransport` subclass so it composes
   cleanly with `httpx.MockTransport` (the project's test-mocking
   standard) and doesn't require swapping the HTTP client library.
4. Tracer-bullet shape: PR1 introduces the layer + adopts in
   `GitHubAdvisoryScanner` (most mature adapter). PR2 rolls out to OSS
   Index, changelog fetcher, registries, license + library-health
   checkers. PR3 retires ad-hoc timeout constants and closes RFC.

## Non-goals

- Replacing `httpx`. The issue is the layer around it, not it.
- Adding `tenacity` or another retry library. Sync-first; doesn't
  compose cleanly with `httpx.AsyncBaseTransport`.
- Connection-pool sharing across adapters. Each adapter still owns its
  own `AsyncClient` (for header isolation — GHSA needs `Authorization`,
  Maven registries don't). Pool reuse *within* an adapter (R6) is fixed
  in PR2 by replacing the per-call `httpx.AsyncClient(...)` in
  `ChangelogFetcher` with a constructor-injected client.
- Changing which HTTP status codes trigger user-visible failures. The
  retry layer is transparent to the adapter — same exceptions, same
  return types, just *fewer* transient failures bubble up.

## Proposed solution

### New package `infrastructure/_shared/http/`

The leading underscore signals "shared internal to infrastructure" —
mirrors the existing `infrastructure/registries/_base.py` precedent.
Four modules:

```
infrastructure/_shared/
├── __init__.py
└── http/
    ├── __init__.py
    ├── policy.py        # HttpPolicy dataclass
    ├── rate_limit.py    # is_rate_limited (lifted from changelog_fetcher)
    ├── transport.py     # ResilientTransport(httpx.AsyncBaseTransport)
    └── client.py        # make_resilient_client(policy, headers) factory
```

### `HttpPolicy`

```python
@dataclass(frozen=True)
class HttpPolicy:
    timeout_seconds: float = 30.0
    max_attempts: int = 3              # initial + 2 retries
    backoff_base_seconds: float = 1.0  # delay = base * 2^attempt, with jitter
    backoff_max_seconds: float = 30.0  # cap
    max_concurrency: int = 20          # consumed by adapters, not the transport
```

Per-adapter overrides via call-site construction: e.g. GHSA uses
`HttpPolicy(timeout_seconds=30.0, max_concurrency=20)`; Maven registries
will use a lower timeout in PR2.

### `is_rate_limited`

Direct lift from `changelog_fetcher.py:77-94` to
`_shared/http/rate_limit.py`. The function moves; the changelog fetcher
re-imports it as `_is_rate_limited` for one PR to keep the existing
test imports (`from ...changelog_fetcher import _is_rate_limited`)
working unchanged. PR2 / PR3 may collapse the alias.

### `ResilientTransport`

Wraps an inner `httpx.AsyncBaseTransport` (defaulting to
`httpx.AsyncHTTPTransport`). On every `handle_async_request`:

1. Call inner.
2. On `httpx.RequestError` (connect timeout, network error): retry up
   to `max_attempts - 1` more times with backoff. After exhaustion,
   re-raise the original error so adapters see the same exception
   type they do today.
3. On HTTP **429** or **5xx** (except 501 Not Implemented): retry with
   backoff. Honor `Retry-After` header if present (seconds or HTTP-date).
4. On 4xx other than 429 (e.g. 404, 401, 403 without rate-limit
   header): **do not retry**. Return the response immediately —
   adapters need to see 404 as a real signal (artifact missing) and 401
   as a real signal (bad token), not retry endlessly.
5. Backoff: `delay = min(backoff_max, backoff_base * 2^(attempt-1))`,
   then **full jitter**: actual sleep is `random.uniform(0, delay)`.
   Implementation uses `asyncio.sleep`; jitter source is `random.random()`
   (seeded only in tests).

The transport is *stateless across requests* — concurrency capping
remains the adapter's responsibility via `asyncio.Semaphore`. This
matches httpx's transport contract (transports are shared across
in-flight requests by default) and avoids the awkward task of making
the transport's internal state thread-safe.

### `make_resilient_client`

```python
def make_resilient_client(
    *,
    policy: HttpPolicy,
    headers: dict[str, str] | None = None,
    follow_redirects: bool = False,
) -> httpx.AsyncClient:
    """Return an AsyncClient wrapping a ResilientTransport."""
```

Returns an `httpx.AsyncClient` configured with:
- `transport=ResilientTransport(policy=policy)`
- `timeout=policy.timeout_seconds` (single value, applied to all stages
  per httpx convention)
- `headers=headers`
- `follow_redirects=follow_redirects`

Adapter usage is a one-line replacement:

```python
# Before
async with httpx.AsyncClient(headers=self._auth_headers(), timeout=30.0) as client:

# After
async with make_resilient_client(
    policy=HttpPolicy(timeout_seconds=30.0),
    headers=self._auth_headers(),
) as client:
```

### PR1 adoption: `GitHubAdvisoryScanner` only

Smallest possible blast radius:

1. Add the four new modules + their tests.
2. Lift `_is_rate_limited` from `changelog_fetcher.py` to
   `_shared/http/rate_limit.py`; re-import in `changelog_fetcher.py`
   to keep test imports working.
3. Replace `GitHubAdvisoryScanner.scan`'s `httpx.AsyncClient(...)`
   construction with `make_resilient_client(...)`.
4. Confirm the existing 23 GHSA tests still pass — they use
   `httpx.MockTransport` and don't observe the retry behaviour because
   the mock returns deterministic responses. New tests cover the retry
   path in `tests/infrastructure/_shared/http/`.

### PR2 rollout (separate RFC step / PR)

`OssIndexScanner`, `ChangelogFetcher` (fixes R6 by holding one client
across the run), `PomLicenseChecker`, `PomInactivityChecker`, both
`MavenMetadataRegistry` subclasses.

### PR3 cleanup (separate RFC step / PR)

Delete every `_HTTP_TIMEOUT = ...` module constant. Document the
HTTP-policy resolution order in `_shared/http/__init__.py`. Mark RFC
Implemented.

## Definition of done (PR1 only)

- [ ] `infrastructure/_shared/http/` package with `policy.py`,
  `rate_limit.py`, `transport.py`, `client.py`, all with module
  docstrings.
- [ ] `tests/infrastructure/_shared/http/` mirror with:
  - `test_rate_limit.py` — 429, 403-with-header, 403-without-header,
    200 baseline.
  - `test_transport.py` — retry on 429 with `Retry-After` honored,
    retry on 503, no retry on 404, exhausts after `max_attempts`,
    backoff+jitter math (seeded random for determinism), retry on
    `httpx.RequestError`.
  - `test_client.py` — factory returns properly-configured client;
    `make_resilient_client` is itself usable in tests via the
    standard `httpx.MockTransport` substitution.
- [ ] `GitHubAdvisoryScanner` uses `make_resilient_client`; existing
  GHSA tests pass unchanged.
- [ ] `changelog_fetcher._is_rate_limited` aliases the shared
  `is_rate_limited`; existing `test_changelog_fetcher.py` imports
  (`_is_rate_limited`, `_RateLimitTracker`) work unchanged.
- [ ] `CHANGELOG.md` `[Unreleased]` ### Added entry for the shared
  HTTP layer (mention that it's only adopted in GHSA so far).
- [ ] All five quality stages pass on the Py 3.11-3.14 CI matrix.

## Open questions

None at PR1 scope. PR2 will need to pick a policy per adapter family
(Maven registries probably want shorter timeout but more attempts;
changelog fetcher is best-effort so fewer attempts).

## Tracer-bullet shape

Three PRs, named in the Phase 7 plan as Steps 3a / 3b / 3c.
