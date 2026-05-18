# RFC-0029: Cache Controls — CLI Flags, Env-Var Root, Per-Source TTL, Negative-Cache Namespacing

**Status:** Implemented
**Created:** 2026-05-18
**Shipped:** 2026-05-18 (PR #63)
**Related JTBDs:** JTBD-3 (reproducible runs), JTBD-5 (operator control)
**Depends on:** RFC-0012 (layered configuration), ADR-0006 (clean architecture)

## Problem

The on-disk cache (currently `diskcache.Cache` instances wired at three sites in `bootstrap.py`) has four operational footguns. None of them block correctness today, but together they make freeze runs hard to reason about under stress:

1. **GHSA + OSS Index scanners ignore `_CACHE_ROOT`.** `bootstrap.py:119` correctly wires `MavenVersionStatusResolver(cache_dir=_CACHE_ROOT / "maven")`, but `_build_scanner` (`bootstrap.py:64-83`) constructs `GitHubAdvisoryScanner(token=…)` and `OssIndexScanner(username=…, api_key=…)` without `cache_dir`. The scanners fall back to their constructor defaults — `Path(".cache/ghsa")` and `Path(".cache/ossindex")` — both **relative to CWD**. The cache root is therefore *three different directories* depending on where the operator runs the CLI from.
2. **No way to bypass or invalidate cache from the CLI.** A fresh CVE landing in GHSA today is invisible for 24 hours after the operator's last run because there's no flag to flush.
3. **No env-var override of cache root.** Hardcoded `Path.home() / ".cache" / "gradle-deps-monitor"`. CI runners that mount `$HOME` read-only or `nix`-style isolated environments can't redirect.
4. **404 negatives share a cache key with positives.** `registries/_base.py:51,63` keys both as `f"{prefix}:{group}:{artifact}"`, distinguishing them by value (empty string = negative). An operator who wants to "purge stale 404s after the upstream artifact recovered" must walk every key. Programmatically possible; operationally invisible.

## Goals

1. CLI controls for the three operations operators actually want: bypass, purge, override TTL.
2. Env-var override of cache root for CI isolation.
3. Per-source TTL configuration via the existing `gradle-deps-monitor.toml` `[cache]` section (already reserved in the loader's `_KNOWN_SECTIONS` per RFC-0012).
4. Fix the bootstrap wiring bug so all three cache sites share `_CACHE_ROOT`.
5. Namespace negative-cache entries separately so the *capability* to selectively purge 404s exists, even though the CLI doesn't expose that operation yet.

## Non-goals

- A `--clear-negatives-only` CLI flag (deferred; namespacing in this RFC unblocks it).
- Per-source TTL on GHSA vs OSS Index individually — they share `ttl_seconds_advisory` for now.
- Cache compression, eviction policy changes, or migration away from `diskcache`.
- Configurable cache key format — keeping today's `{prefix}:{group}:{artifact}` shape.

## Proposed solution

### Domain layer — new `CacheConfig` DTO

Extend `domain/config.py` with one immutable dataclass added to `AppConfig`:

```python
@dataclass(frozen=True)
class CacheConfig:
    """Persistent-cache tunables. Empty config = built-in defaults."""

    root: Path | None = None              # None → resolve default (see below)
    ttl_seconds_maven: int = 3600         # 1 h — Maven metadata XML
    ttl_seconds_advisory: int = 86_400    # 24 h — GHSA + OSS Index
```

Reads remain on the `bool enabled` axis when `--no-cache` is in effect: the flag at the CLI doesn't set this field. Instead, `bootstrap.py` redirects the cache to an ephemeral `tempfile.mkdtemp()` for the run, so the persistent cache is untouched. This keeps the cache adapters dumb — they always cache, they just sometimes cache into `/tmp/gradle-deps-monitor-nocache-XXXXXX`.

### Cache helpers — new module `infrastructure/cache/`

Single new file `infrastructure/cache/cache_paths.py` exposing:

| Function | Purpose |
|---|---|
| `default_cache_root() -> Path` | Reads `GRADLE_DEPS_MONITOR_CACHE_ROOT` env var; falls back to `Path.home() / ".cache" / "gradle-deps-monitor"`. |
| `resolve_cache_root(cfg: CacheConfig) -> Path` | Applies resolution order: env var > `cfg.root` > default. |
| `clear_cache(root: Path) -> int` | `shutil.rmtree(root, ignore_errors=True)`; returns bytes freed for the CLI to display. |
| `ephemeral_cache_root() -> Path` | `tempfile.mkdtemp(prefix="gradle-deps-monitor-nocache-")`. Caller arranges cleanup. |

No changes to existing scanner/registry adapters — they continue to accept `cache_dir: Path` constructor arguments. The new module's job is to *compute* that path.

### Negative-cache namespacing — `registries/_base.py`

The cache key today is `f"{self._CACHE_PREFIX}:{group}:{artifact}"`. Change to:

- **Positive** entries: `f"{self._CACHE_PREFIX}:ok:{group}:{artifact}"`
- **Negative** entries (404): `f"{self._CACHE_PREFIX}:404:{group}:{artifact}"`

Add one method to `MavenMetadataRegistry`:

```python
def clear_negative_entries(self) -> int:
    """Delete cached 404 entries; return count purged."""
    prefix = f"{self._CACHE_PREFIX}:404:"
    removed = 0
    for key in list(self._cache):
        if isinstance(key, str) and key.startswith(prefix):
            del self._cache[key]
            removed += 1
    return removed
```

The CLI does *not* expose this in PR1 — it's an internal API for a future `--clear-negatives` flag or a programmatic operator script. Shipping it now means the key-format migration is captured in one PR.

**Cache-format compatibility:** existing on-disk caches use the old key shape and will become orphans after this change. Acceptable because (a) entries expire on their TTL (Maven 1h), (b) the orphans are functionally invisible (no code reads them), (c) `shutil.rmtree(root)` is the documented escape hatch via `--clear-cache`.

### TOML loader — parse `[cache]` section

`infrastructure/config/loader.py` currently lists `cache` in `_KNOWN_SECTIONS` but skips it. Add `_parse_cache(section, path) -> CacheConfig` mirroring the `_parse_risk_weights` shape: validate types, warn on unknown keys, return defaults when section is missing or empty.

Supported keys:

```toml
[cache]
root = "/var/cache/gradle-deps-monitor"     # absolute path
ttl_seconds_maven = 3600
ttl_seconds_advisory = 86400
```

### Bootstrap — fix wiring + accept `CacheConfig`

`bootstrap.py` changes:

1. Drop the module-level `_CACHE_ROOT` constant. Compute it per-call via `resolve_cache_root(cfg.cache)`.
2. `create_check_command` gains parameters: `no_cache: bool = False`, `clear_cache_first: bool = False`, `cache_ttl_override: int | None = None`.
3. If `clear_cache_first`: call `clear_cache(resolved_root)` *before* constructing adapters.
4. If `no_cache`: replace `resolved_root` with `ephemeral_cache_root()` and register `atexit.register(shutil.rmtree, ..., ignore_errors=True)` for cleanup.
5. Wire `_CACHE_ROOT` to **all three** cache sites: `MavenVersionStatusResolver(cache_dir=root/"maven", ttl=…)`, `GitHubAdvisoryScanner(token=…, cache_dir=root/"ghsa", ttl=…)`, `OssIndexScanner(username=…, api_key=…, cache_dir=root/"ossindex", ttl=…)`. Closes the wiring bug.
6. If `cache_ttl_override is not None`: pass that TTL to every adapter, overriding per-source defaults.

### CLI flags — `cli.py` `check` command

Three new flags, all with sensible defaults:

```bash
gradle-deps-monitor check gradle --no-cache        # ephemeral cache, persistent untouched
gradle-deps-monitor check gradle --clear-cache     # purge persistent before run
gradle-deps-monitor check gradle --cache-ttl 60    # all cache writes use 60s TTL
```

`--no-cache` and `--clear-cache` together are valid (purge first, then use ephemeral cache anyway — slightly redundant but not an error).

`diff` command stays unchanged — it does no network I/O.

### Resolution order (documented in docstring)

For cache root:
1. `GRADLE_DEPS_MONITOR_CACHE_ROOT` env var (highest priority)
2. `[cache] root` from `gradle-deps-monitor.toml`
3. `~/.cache/gradle-deps-monitor` (lowest)

For TTL:
1. `--cache-ttl SECONDS` (highest; overrides all sources for this run)
2. `[cache] ttl_seconds_*` per source
3. Constructor defaults (Maven 3600, advisory 86400)

## Definition of done

- [ ] `domain/config.py` exports `CacheConfig`; `AppConfig.cache: CacheConfig = field(default_factory=CacheConfig)`.
- [ ] `infrastructure/cache/cache_paths.py` exists with the four functions above + unit tests.
- [ ] `infrastructure/config/loader.py` parses `[cache]` section; unknown keys warn; tests cover missing / empty / valid / typo cases.
- [ ] `infrastructure/registries/_base.py` uses `:ok:` / `:404:` key prefixes; `clear_negative_entries()` method added with a unit test.
- [ ] `bootstrap.py` `create_check_command` accepts the three flag parameters, computes cache root once via `resolve_cache_root`, wires *all three* cache sites consistently.
- [ ] `cli.py` `check` exposes `--no-cache` / `--clear-cache` / `--cache-ttl`; CLI tests confirm the flags reach bootstrap.
- [ ] `CHANGELOG.md` `[Unreleased]` ### Added entry mentions the three flags, the env-var, and the `[cache]` TOML section. ### Fixed entry mentions the GHSA + OSS Index `_CACHE_ROOT` wiring bug.
- [ ] `README.md` Credentials/Configuration sections gain a one-paragraph cache subsection.
- [ ] All five quality stages pass on Py 3.11/3.12/3.13/3.14 CI matrix.

## Open questions

None currently. Negative-cache CLI exposure deferred to a follow-up; per-source TTL granularity (GHSA vs OSS Index separately) deferred.

## Tracer-bullet shape

Single PR. The scope is small enough (~150-200 LOC + tests) that splitting buys nothing. RFC-0030 (HTTP resilience) is the bigger tracer right after this.
