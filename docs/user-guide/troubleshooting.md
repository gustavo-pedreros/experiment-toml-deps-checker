# Troubleshooting

What each common message means and what to do about it. Grouped by
where the message surfaces.

## "Could not find libs.versions.toml"

The CLI exits with code `3` and a message like:

```
Error: gradle/libs.versions.toml not found under <path>
```

Cause: you pointed `check` at the project root instead of the
Gradle directory.

Fix: pass the **directory that contains `libs.versions.toml`**,
typically `<project>/gradle/`.

```bash
# Wrong — points at project root
gradle-deps-monitor check .

# Right — points at the Gradle directory
gradle-deps-monitor check ./gradle
```

## "Security scan not configured"

The Markdown report renders:

```
## Security

> ⊘ Security scan not configured — set GITHUB_TOKEN to enable the
> GitHub Advisory Database integration, or OSS_INDEX_USER +
> OSS_INDEX_API_KEY to enable Sonatype OSS Index. Re-run to
> populate this section.
```

Cause: neither `GITHUB_TOKEN` / `GH_TOKEN` nor the OSS Index pair
is set in the environment.

Fix: set at least one. See
[Configuration → Environment variables](configuration.md#environment-variables).
The token needs **zero scopes** — its only job is to lift the
rate limit, not to authenticate.

## "N of M release notes fetched … fell back to repo URL"

The Major Upgrades section shows:

```
> ⚠️ 5 of 12 release notes fetched; 7 fell back to repo URL due to
> GitHub rate limit. Set GITHUB_TOKEN to raise the limit (60 →
> 5 000 req/h) and get full release-note coverage on the next run.
```

Cause: anonymous GitHub API requests cap at 60/hour, and the
scraper hit that cap. The report is still correct — affected
libraries just show a bare repo URL instead of a quoted snippet.

Fix: set `GITHUB_TOKEN`. The cap goes from 60 to 5 000 req/h, which
covers a multi-thousand-library catalog with headroom.

## Risk Score is 0 for every library

You ran `--risk-score` but the table is full of zeros.

Cause: `--risk-score` enables the scoring **engine**, but the CVE
dimension (the heaviest at weight 30) is zero when no CVE scanner
is wired. Without `GITHUB_TOKEN` / OSS Index creds, the engine has
nothing to score.

Fix: set CVE credentials before re-running. The CLI prints a
warning to stderr when this situation is detected:

```
Warning: --risk-score is enabled but no CVE advisory credentials
are set. The CVE dimension will score 0 for every library. Set
GITHUB_TOKEN (or GH_TOKEN) and/or OSSINDEX_USER + OSSINDEX_API_KEY
to populate it.
```

## "Cache root … is read-only" / permission errors on cache

CI runners with read-only `$HOME` (Nix-style isolation, some
container images) fail at startup trying to create
`~/.cache/gradle-deps-monitor`.

Fix: redirect the cache root via env var:

```bash
export GRADLE_DEPS_MONITOR_CACHE_ROOT=/tmp/gradle-deps-monitor-cache
gradle-deps-monitor check ./gradle
```

Or per-run-only (no persistent cache):

```bash
gradle-deps-monitor check ./gradle --no-cache
```

`--no-cache` writes to a tempdir cleaned up at exit. Use it when
the read-only filesystem also extends to `/tmp` writes you can't
clean up yourself.

## `--warn-on` rejects my category name

Exit code `2` with:

```
Usage error: Invalid value for '--warn-on': Unknown warning
category 'cves'. Valid: breaking, compliance, deprecated,
high-vulnerability, library-health, license, toolchain.
```

Cause: the seven valid category names are listed in the error —
common mistakes are pluralisation (`cves` vs `high-vulnerability`)
and underscores (`library_health` vs `library-health`).

Fix: use the exact names. Categories are comma-separated:

```bash
gradle-deps-monitor check ./gradle --warn-on high-vulnerability,deprecated,breaking
```

## `--fail-on-errors` failed but I want a clean run

The build went red because of a critical CVE or a strong-copyleft
license. You want to suppress that one finding without dropping
the gate entirely.

The honest answer for v1: there is no per-finding suppression
mechanism. Either fix the underlying issue (upgrade the library,
swap to a permissively-licensed alternative, etc.) or remove
`--fail-on-errors` for that run.

The v2 expression DSL (`--fail-on "risk_score > 80 AND severity ==
critical AND coordinate != 'allowed:lib'"`) is the planned answer
for per-finding policy carve-outs; it's tracked as a follow-up RFC.

## Diff says "no changes" but I know there are changes

`gradle-deps-monitor diff` compares two `freeze.json` snapshots.
"No changes" can mean:

- The two snapshots really are identical (the legitimate case).
- The new snapshot's CVE scan didn't run (no creds) while the old
  one did. Add `GITHUB_TOKEN` to both runs.
- One snapshot was truncated mid-write before atomic writes shipped.
  Re-run on a version that includes RFC-0032 (`gradle-deps-monitor
  --version` → at least the version where RFC-0032 was implemented).

## Cold runs are slow (~ 9 s on a 200-library catalog)

This is the expected ballpark for a **cold** cache run on the
validation corpus. Warm runs land at around 5 s for the same input.

If your cold run takes meaningfully longer (e.g. > 30 s), check:

- **HTTP timeouts firing** — the report's Library Health section
  shows a `inactive` signal for libraries the tool couldn't reach.
  Common culprit: corporate proxy not letting Maven Central
  through.
- **Rate limit headroom** — anonymous GitHub gets 60 req/h; once
  exhausted every changelog scrape spends the full retry budget
  before falling back. `GITHUB_TOKEN` fixes this.
- **DNS resolution slowness** — the resilient transport
  (RFC-0030) retries with backoff on `httpx.RequestError`, so DNS
  thrash compounds. Pinning a faster DNS or pre-warming with a
  single `curl https://repo.maven.apache.org/...` before the run
  helps in pathological environments.

## Still stuck

Open an issue at
[github.com/gustavo-pedreros/experiment-toml-deps-checker/issues](https://github.com/gustavo-pedreros/experiment-toml-deps-checker/issues)
with:

- `gradle-deps-monitor --version`
- The command you ran.
- The full console output (use `--no-cache` to remove any cache
  noise from the repro).
- Whether `GITHUB_TOKEN` was set (don't share the token itself).
