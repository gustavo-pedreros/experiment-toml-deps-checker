# Configuration

`gradle-deps-monitor` reads three sources for tunables, applied in
order so higher steps override lower ones (RFC-0012):

1. Built-in defaults.
2. `gradle-deps-monitor.toml` at the project root.
3. Environment variables (where applicable).
4. CLI flags.

This page is the complete reference for steps 2 and 3. CLI flags are
documented inline in `gradle-deps-monitor check --help` and on the
[Getting Started](getting-started.md) page.

## `gradle-deps-monitor.toml`

Place the file at the **project root** (the parent of your `gradle/`
directory). The CLI loads it automatically from
`<catalog-path>/../gradle-deps-monitor.toml`. Every section is
optional; missing sections fall back to the documented defaults.

### `[risk]` — Risk-score weights and thresholds (opt-in via `--risk-score`)

```toml
[risk]
# Per-dimension caps. Must sum to exactly 100; the loader rejects
# the file otherwise.
outdatedness = 25
cve          = 30
abandonment  = 15
blast_radius = 15
compliance   = 10
license      = 5

# Score cutoffs that classify a library into LOW / MEDIUM / HIGH /
# CRITICAL. Must satisfy medium <= high <= critical.
critical_threshold = 70
high_threshold     = 50
medium_threshold   = 30
```

The defaults above are what the tool uses when the section is
omitted. Pick weights to match what your team actually cares about
— a security-first project might raise `cve` and lower
`outdatedness`; a compliance-first project the inverse.

Risk scoring is experimental (ADR-0004). It is most informative when
compared across multiple freezes — a single number in isolation is
less useful than the trend.

### `[cache]` — Persistent-cache controls (RFC-0029)

```toml
[cache]
# Where on-disk cache files live. Absolute path. When unset,
# the env var GRADLE_DEPS_MONITOR_CACHE_ROOT wins; when that is
# also unset, ~/.cache/gradle-deps-monitor is used.
root = "/var/cache/gradle-deps-monitor"

# TTL in seconds for Maven Central + Google Maven responses.
# Defaults to 1 h — Maven metadata is updated continuously but
# moves slowly for any given coordinate.
ttl_seconds_maven = 3600

# TTL in seconds for GHSA + OSS Index responses.
# Defaults to 24 h. Bypass with --no-cache for a fresh-CVE run.
ttl_seconds_advisory = 86400
```

The persistent cache makes warm runs roughly **2–3× faster** than
cold ones on the validation corpus (170 libraries: ~5 s warm vs.
~9 s cold). It is safe to share across projects — entries are keyed
by Maven coordinate, not by your catalog.

### `[output]` — Opt-in output writers (RFC-0034)

```toml
[output]
# When true, also emit freeze-slack.json (Slack Block Kit).
# When false (default), the Slack writer is skipped.
# CLI: --slack / --no-slack overrides this value.
slack = true
```

The four "load-bearing" outputs (`freeze.md`, `freeze.json`,
`freeze-inventory.csv`, `freeze-findings.csv`) are always emitted —
the diff command and the `/analyze-freeze` skill depend on them.
Only Slack is exposed as opt-in today. The same shape will extend
to the planned HTML export when RFC-0010 lands
(`[output] html = true`).

### Unknown keys

Unknown top-level sections or keys are logged as warnings, not
errors — your config file survives forward-compatible additions
without needing to upgrade in lockstep with the tool.

## Environment variables

| Variable | Where it lands | Notes |
|---|---|---|
| `GITHUB_TOKEN` | GHSA CVE scanner + changelog scraper rate limit | Zero scopes required. |
| `GH_TOKEN` | Same as above | Alias accepted to match `gh` CLI's convention. |
| `OSSINDEX_USER` | OSS Index CVE scanner | Pair with `OSSINDEX_API_KEY`. |
| `OSSINDEX_API_KEY` | OSS Index CVE scanner | Pair with `OSSINDEX_USER`. |
| `GRADLE_DEPS_MONITOR_CACHE_ROOT` | Cache root directory | Overrides `[cache] root` from TOML. CI runners with read-only `$HOME` or Nix-style isolated environments use this. |
| `GITHUB_ACTIONS` | Triggers `::error` / `::warning` workflow-command output when set to `"true"` | GitHub Actions sets this automatically. |

All credentials are read once at startup; no other env var influences
runtime behaviour.

## Cache CLI flags (per-invocation overrides)

These do not live in the config file — they are per-run overrides
exposed on the `check` command (RFC-0029):

```bash
# Bypass the persistent cache for this run only. Adapters write to
# a tempdir cleaned up at exit; the persistent cache is untouched.
gradle-deps-monitor check /path/to/gradle --no-cache

# Purge the persistent cache before the run, then rebuild fresh.
gradle-deps-monitor check /path/to/gradle --clear-cache

# Override every adapter's TTL for this run (seconds). Useful for
# CI runs that want fresh CVE data without wiping the cache.
gradle-deps-monitor check /path/to/gradle --cache-ttl 60
```

`--no-cache` and `--clear-cache` together are valid (purge first,
then use ephemeral cache — slightly redundant but not an error).

## Diff command

`gradle-deps-monitor diff` does no network I/O and is unaffected by
the `[cache]` section, cache CLI flags, and credential env vars.

```bash
# Compare two freezes
gradle-deps-monitor diff new/freeze.json --prev old/freeze.json

# Baseline (single freeze, no prior)
gradle-deps-monitor diff first/freeze.json
```

Outputs land alongside `check` outputs by default (`./reports/`):
`freeze-diff.md`, `freeze-diff.json`. Add `--slack` (or
`[output] slack = true` in a `gradle-deps-monitor.toml` at the cwd)
to also emit `freeze-diff-slack.json` per RFC-0034.
