# Getting started

This page takes you from "never heard of the tool" to a complete
freeze report in under five minutes.

## Prerequisites

| Requirement | Minimum |
|---|---|
| Python | 3.11 (also tested on 3.12 / 3.13 / 3.14 in CI) |
| OS | Linux, macOS, or Windows |
| Network access | `repo.maven.apache.org`, `maven.google.com`, optional GitHub / OSS Index for CVE scans |
| Gradle project shape | Version catalog at `<project>/gradle/libs.versions.toml` (Gradle 7.4+) |

Credentials are **not required** for a first run: the CVE scanner and
GitHub-rate-limit-aware changelog scraper degrade gracefully when no
token is set. See [Credentials](#credentials) below to unlock them.

## Install

Pick whichever fits your workflow.

### From PyPI (recommended)

```bash
pip install gradle-deps-monitor
```

### Isolated install with `pipx`

```bash
pipx install gradle-deps-monitor
```

### From source (contributors)

```bash
git clone https://github.com/gustavo-pedreros/experiment-toml-deps-checker.git
cd experiment-toml-deps-checker
pip install -e ".[dev]"
```

Verify the install:

```bash
gradle-deps-monitor --version
```

## First run

Point the CLI at the **directory that contains `libs.versions.toml`**
(typically `<your-project>/gradle/`):

```bash
gradle-deps-monitor check /path/to/your/project/gradle
```

By default, reports land in `./reports/`. Override with `--out`:

```bash
gradle-deps-monitor check /path/to/your/project/gradle --out freeze-reports/$(date +%Y-%m-%d)
```

A successful run produces a Rich console summary plus four files
(five with `--slack`):

| File | Format | What it is |
|---|---|---|
| `freeze.md` | Markdown | Human-readable canonical report (one section per check) |
| `freeze.json` | JSON | Machine-readable snapshot, SemVer-versioned per ADR-0008 |
| `freeze-inventory.csv` | CSV | One row per catalog library, all dimensions joined (RFC-0017) |
| `freeze-findings.csv` | CSV | One row per finding across every section (RFC-0017) |
| `freeze-slack.json` *(opt-in via `--slack`)* | JSON (Block Kit) | Slack-friendly summary, post via incoming webhook (RFC-0034) |

The Markdown report is the canonical one for humans; the JSON is the
canonical one for tooling (its schema follows SemVer — see
[ADR-0008](../adr/0008-json-schema-semver.md)).

Pass `--slack` (or set `[output] slack = true` in your config — see
[Configuration](configuration.md)) to also emit the Block Kit JSON
for posting to a Slack incoming webhook.

## Reading the console summary

The summary that prints to your terminal is a one-screen executive
view, designed to be glance-able. Each line maps to a section of the
full Markdown report:

```
╭─ Gradle Dependency Freeze Report ─╮
│ Generated  2026-05-18T19:00:00    │
│ Libraries  170                    │
│ Plugins    8                      │
╰───────────────────────────────────╯

Outdated (42)        12 major, 18 minor, 12 patch
Catalog Health       ✅ no findings
Security             80 low (avg 8.8, max 23.0)
Play Store           ❗ 1 violation
Toolchain            ✅ no findings
Library Health       ⚠ 3 deprecated
Major Upgrades       4 likely-breaking, 12 other

Reports written → reports/
  • freeze.md  • freeze.json
  • freeze-inventory.csv  • freeze-findings.csv
```

The icons follow the unified severity vocabulary across sections
(`✅` clean / `⚠` warning / `❗` violation / `⊘` not configured) —
[RFC-0016b](../proposals/0016-severity-style.md) for the design.

## Credentials

Two optional integrations unlock significantly more signal:

| Variable | Source | What it enables |
|---|---|---|
| `GITHUB_TOKEN` (or `GH_TOKEN`) | GitHub fine-grained PAT, **zero scopes** required | GHSA CVE scan + 5 000 req/h changelog scrape |
| `OSSINDEX_USER` + `OSSINDEX_API_KEY` | Sonatype account | OSS Index CVE scan (composes with GHSA when both are set) |

Without `GITHUB_TOKEN`, GitHub still answers 60 anonymous requests
per hour and the report tells you so (`⚠ N of M release notes
fetched … fell back to repo URL`). The CVE section renders an
explicit `⊘ scan not configured` instead of silently being empty.

The GHSA scope requirement is **zero** — the token only exists to
raise the rate limit, not to authenticate against your repos.

Set them however your shell prefers:

```bash
export GITHUB_TOKEN=ghp_xxx
gradle-deps-monitor check /path/to/gradle
unset GITHUB_TOKEN
```

## Opt-in flags

Two heavier checks are disabled by default because they cost time
on large catalogs:

```bash
# Static-scan every build.gradle(.kts) file for catalog accessor usage.
gradle-deps-monitor check /path/to/gradle --module-usage

# Compute a 0-100 composite Risk Score per library across six
# weighted dimensions (experimental — see ADR-0004).
gradle-deps-monitor check /path/to/gradle --risk-score

# Combine them.
gradle-deps-monitor check /path/to/gradle -m -r
```

`-m` and `-r` are the short flags.

## Exit codes

Following the `sysexits.h` convention (RFC-0018 v1):

| Code | Meaning |
|---|---|
| `0` | Success |
| `1` | Policy violation — `--fail-on-errors` triggered |
| `2` | Usage error — bad flag value (e.g. unknown `--warn-on` category) |
| `3` | Configuration error — `libs.versions.toml` missing or unreadable |

Add `--fail-on-errors` to make the CLI break the build on any
error-level finding:

```bash
gradle-deps-monitor check /path/to/gradle --fail-on-errors
```

## Next steps

- Read the full [list of checks](../../README.md#what-it-checks) in
  the README.
- The **Configuration**, **Feature deep-dives**, **CI integration**,
  and **Troubleshooting** chapters land in the next PR
  (RFC-0021 Phase 2).
- Browse the [architecture diagrams](../diagrams/) for a visual
  overview of how the tool is laid out internally.
