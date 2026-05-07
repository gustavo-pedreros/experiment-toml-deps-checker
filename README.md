# gradle-deps-monitor

**Freeze-time technical due-diligence report for Android / Gradle projects.**

Analyses a `libs.versions.toml` version catalog, checks every dependency against Maven Central and Google Maven, audits catalog health, scans for CVEs, validates Play Store compliance, checks toolchain compatibility, detects deprecated and abandoned libraries, diffs reports between freezes, and writes structured reports — Markdown, JSON, and Slack Block Kit — ready to commit or post automatically via CI.

---

## Features

- **Version status** — for every library, resolves the latest stable release from Maven Central / Google Maven (Google-first for `androidx.*` / `com.google.*` / `com.android.*`, Central-first elsewhere) and classifies drift as `none` / `patch` / `minor` / `major`. Drives the outdatedness dimension of the risk score and powers the per-run "Outdated" summary in every output format. Also flags pinned versions that are `alpha`, `beta`, `rc`, `dev`, or `SNAPSHOT`
- **Catalog health audit** — 9 pluggable rules that surface structural problems: duplicate libraries, unresolved `version.ref` keys, orphan version entries, inconsistent alias naming, missing plugins/bundles, unresolved BoM children, and more
- **CVE scan** — queries GitHub Advisory Database and OSS Index for known vulnerabilities in every pinned library; requires credentials (see [Credentials](#credentials-and-environment-variables))
- **Play Store compliance** — detects deprecated libraries (e.g. SafetyNet → Play Integrity) and checks `targetSdk` against Google's published requirements; `targetSdk` is auto-detected from the `[versions]` block of the TOML (keys like `targetSdk`, `android-targetSdk`, `targetSdkVersion` are all recognised); library-specific findings carry the catalog `alias`, so the risk score's compliance dimension contributes per-library (RFC-0015)
- **Toolchain compatibility** — validates Kotlin ↔ Compose Compiler (bundled `kotlin-compose.yaml` matrix), Kotlin ↔ KSP (prefix-match rule), and AGP ↔ Gradle wrapper (bundled `agp-gradle.yaml` matrix); Kotlin / AGP / KSP / Compose versions are read from the TOML `[versions]` block; Gradle version is read from `gradle/wrapper/gradle-wrapper.properties`
- **Library health** — detects deprecated, relocated, and abandoned libraries via a curated knowledge base (26 Android-specific entries), Maven POM `<relocation>` tag detection, and an inactivity heuristic based on `maven-metadata.xml` (no credentials required)
- **Maven BoM support** — detects BoM entries (artifact name ends in `-bom` / `-platform`), fetches the BoM's POM and parses `<dependencyManagement>`, then enriches the catalog so children declared without a version inherit it from the BoM. Reports show the parent–child relationship (`via firebase-bom 33.0.0`) and the risk score outdatedness for managed children mirrors the BoM's drift, so bumping a BoM is one actionable item instead of N. Catalog Health rule `catalog.unresolved-bom-child` flags orphan children if the BoM is later removed
- **Changelog scraper** — for every library with a major upgrade available, discovers the release notes via the GitHub Releases API or a `CHANGELOG.md` fallback; applies a breaking-change heuristic (🔴 likely breaking / 🟢 clean / ⚪ unknown); `GITHUB_TOKEN` is optional but increases the API rate limit
- **Freeze diff** — compares two freeze reports (`freeze.json`) and produces a diff report; first-run mode establishes a baseline when no previous report exists (see [Diff between freezes](#diff-between-freezes))
- **Module usage map** _(opt-in: `--module-usage`)_ — static analysis of `build.gradle(.kts)` files; shows how many modules use each library via `implementation`, `api`, or test configurations; identifies the heaviest dependency modules
- **License audit** — fetches Maven POM `<licenses>` metadata for every pinned library and classifies licenses into tiers (Permissive / Weak copyleft / Strong copyleft / Unknown); flags GPL/AGPL dependencies automatically, with Google Maven fallback for `androidx`/`com.google.*` groups
- **Risk score** _(opt-in: `--risk-score`)_ — composite 0-100 score per library derived from six dimensions: outdatedness, CVE severity, abandonment, blast radius, compliance, and license tier; top-10 breakdown shown in all report formats with configurable weights and thresholds (experimental — see ADR-0004)
- **Multiple output formats** — Markdown (human-readable), JSON (machine-readable, schema-versioned), and Slack Block Kit (webhook-ready)
- **Rich console summary** — colour-coded executive summary printed at the end of every run
- **On-disk HTTP cache** — avoids redundant Maven registry calls; configurable TTL
- **Zero Bash dependency** — single Python CLI, no wrapper scripts

---

## Quick start

### Requirements

- Python 3.11+
- Access to Maven Central and Google Maven (internet)

### Install

```bash
pip install gradle-deps-monitor
```

Or, for local development:

```bash
git clone https://github.com/gustavo-pedreros/toml-deps-checker.git
cd toml-deps-checker
pip install -e ".[dev]"
```

### Run

```bash
gradle-deps-monitor check /path/to/gradle
```

`/path/to/gradle` is the directory that contains `libs.versions.toml` (e.g. `app/gradle` or just `gradle`).

By default, reports are written to `./reports/`. Use `--out` to change the destination:

```bash
gradle-deps-monitor check /path/to/gradle --out freeze-reports/2026-05-04
```

#### Opt-in features

Two features are disabled by default because they require extra work (file scanning or score computation):

```bash
# Include a module usage map (scans all build.gradle(.kts) files)
gradle-deps-monitor check /path/to/gradle --module-usage

# Include a composite risk score per library (experimental)
gradle-deps-monitor check /path/to/gradle --risk-score

# Both at once
gradle-deps-monitor check /path/to/gradle --module-usage --risk-score
```

#### Per-project configuration

Drop a `gradle-deps-monitor.toml` next to your Gradle directory (i.e. at the project root) to override risk-score weights and thresholds. The file is optional; when absent, calibrated defaults apply.

```toml
# gradle-deps-monitor.toml — every section is optional.

[risk_weights]   # must sum to 100
outdatedness = 20
cve          = 40    # bumped for fintech / regulated apps
abandonment  = 15
blast_radius = 10
compliance   = 10
license      = 5

[risk_thresholds]   # must satisfy medium ≤ high ≤ critical
critical = 80
high     = 60
medium   = 40
```

Resolution order: built-in defaults → `gradle-deps-monitor.toml` → environment variables → CLI flags. See [RFC-0012](docs/proposals/0012-layered-configuration.md).

---

## Credentials and environment variables

| Variable | Required for |
|----------|-------------|
| `GITHUB_TOKEN` or `GH_TOKEN` | CVE scan via GitHub Advisory Database; also raises the rate limit for the changelog scraper |
| `OSSINDEX_USER` + `OSSINDEX_API_KEY` | CVE scan via Sonatype OSS Index |

When both a GitHub token **and** OSS Index credentials are set, results from both sources are merged. When neither is set, the Security section is omitted from the report and the CVE dimension of the risk score is 0. Running `--risk-score` without credentials emits a warning.

```bash
export GITHUB_TOKEN=ghp_...
gradle-deps-monitor check gradle --out freeze-reports/$(date +%Y-%m-%d) --risk-score
```

---

## Output

### Console (`check`)

The console output adapts to what was found. A full run prints panels for each section — catalog health, security advisories, Play Store compliance, toolchain, library health, major upgrades, module usage map, license audit, and risk score — each colour-coded by severity. A clean run is concise:

```
╭─ Gradle Dependency Freeze Report ─╮
│ Generated  2026-05-04T10:00:00    │
│ Libraries  42                      │
│ Plugins    6                       │
│ Bundles    3                       │
╰────────────────────────────────────╯

Outdated (3)
  2 major  1 minor  0 patch

Catalog Health — no issues found
Security — no known vulnerabilities
Play Store Compliance — 1 finding(s): 1 violation(s)
  ERROR  PLAY-DEP-001  SafetyNet detected → migrate to Play Integrity API

Reports written → freeze-reports/2026-05-04
  • freeze.md
  • freeze.json
  • freeze-slack.json
```

### Files written (`check`)

| File | Format | Purpose |
|------|--------|---------|
| `freeze.md` | Markdown | Human-readable report; commit to `freeze-reports/` |
| `freeze.json` | JSON (`schema_version: "1.4.0"`) | CI parsing, dashboards |
| `freeze-slack.json` | Slack Block Kit | Post via incoming webhook |

The JSON `schema_version` follows SemVer per [ADR-0008](docs/adr/0008-json-schema-semver.md): MINOR bumps are additive (new fields), MAJOR bumps are breaking. Consumers reading `1.x` MUST tolerate unknown fields and unknown enum values.

---

## Diff between freezes

The `diff` command compares two `freeze.json` reports and writes a comparative summary.

```bash
# First run — establish a baseline (no previous report yet)
gradle-deps-monitor diff freeze-reports/2026-05-04/freeze.json \
  --out freeze-reports/2026-05-04

# Subsequent runs — compare current against previous
gradle-deps-monitor diff freeze-reports/2026-05-18/freeze.json \
  --prev freeze-reports/2026-05-04/freeze.json \
  --out freeze-reports/2026-05-18
```

The baseline console output:

```
╭─ 🌱 Baseline Established ─╮
│ Generated  2026-05-04T10:00:00 │
╰────────────────────────────────╯

This is the first registered freeze report.
Future diff reports will compare against this baseline.

Reports written → freeze-reports/2026-05-04
  • freeze-diff.md
  • freeze-diff.json
  • freeze-diff-slack.json
```

A comparison console output:

```
╭─ Freeze Diff ──────────────────────────╮
│ Before  2026-05-04T10:00:00            │
│ After   2026-05-18T10:00:00            │
╰────────────────────────────────────────╯

Libraries — 4 upgraded (1 major, 2 minor, 1 patch), 1 added
  major  retrofit  2.9.0 → 3.0.0

Plugins — no changes
Catalog Health — 1 introduced, 0 resolved

Reports written → freeze-reports/2026-05-18
  • freeze-diff.md
  • freeze-diff.json
  • freeze-diff-slack.json
```

### Files written (`diff`)

| File | Format | Purpose |
|------|--------|---------|
| `freeze-diff.md` | Markdown | Human-readable diff; commit alongside `freeze.md` |
| `freeze-diff.json` | JSON (`schema_version: "1.1.0"`) | CI parsing, trend dashboards |
| `freeze-diff-slack.json` | Slack Block Kit | Post diff summary to your channel |

---

## Catalog health rules

| Rule ID | Severity | Description |
|---------|----------|-------------|
| `HDX-001` | error | Duplicate library (`group:artifact` appears more than once) |
| `HDX-002` | error | Unresolved `version.ref` (points to a missing `[versions]` key) |
| `HDX-003` | warning | Inconsistent alias naming (mix of `camelCase` and `kebab-case`) |
| `HDX-004` | warning | No `[plugins]` block in a non-empty catalog |
| `HDX-005` | warning | Orphan version key (declared in `[versions]` but never referenced) |
| `HDX-006` | info | Inline version literals (prefer `version.ref` for deduplication) |
| `HDX-007` | info | No `[bundles]` block (multi-library catalog) |
| `HDX-008` | suggestion | Duplicate version values (different keys share the same version string) |
| `catalog.unresolved-bom-child` | error | Library declared without a version and no BoM resolved it (RFC-0014) |

---

## Toolchain compatibility rules

Validated automatically on every run. No credentials required.
All version values (Kotlin, AGP, KSP, Compose Compiler) are read from the TOML `[versions]` block; key names are normalised (case-insensitive, separators stripped).

| Rule ID | Check | How it works |
|---------|-------|-------------|
| `TOOL-KC-001` | Kotlin ↔ Compose Compiler | Kotlin 2.x: plugin version must match Kotlin exactly. Kotlin 1.x: looked up in the bundled `kotlin-compose.yaml` matrix |
| `TOOL-KSP-001` | Kotlin ↔ KSP | KSP version string must start with the Kotlin version prefix (e.g. `2.1.10-1.0.29` for Kotlin `2.1.10`) |
| `TOOL-AGP-001` | AGP ↔ Gradle wrapper | Gradle version is read from `gradle/wrapper/gradle-wrapper.properties` and checked against the bundled `agp-gradle.yaml` matrix |

The bundled matrices cover Kotlin 1.7–2.x and AGP 7.0–8.9. Matrix files live in `src/gradle_deps_monitor/data/compatibility/` and can be updated via PR as new toolchain versions are released.

---

## Library health detection

Three signals are combined on every run. No credentials required.

| Signal | Source | Examples |
|--------|--------|---------|
| **Curated KB** | Bundled `library_health_kb.yaml` (26 entries) | ButterKnife, Dagger-Android, RxJava 1.x/2.x, legacy Fabric SDK, Android Support Library, Android Arch → AndroidX |
| **POM relocation** | Maven POM `<distributionManagement><relocation>` tag | Detects any library that published a redirect on Maven Central |
| **Inactivity** | `maven-metadata.xml` `<lastUpdated>` field | MEDIUM (≥ 730 days, ~24 months), HIGH (≥ 1095 days, ~36 months — likely abandoned) |

Google-hosted libraries (`androidx.*`, `com.google.*`, etc.) are excluded from the inactivity check.
The curated KB lives in `src/gradle_deps_monitor/data/library_health_kb.yaml` and can be extended via PR.

---

## CI integration (Bitrise / GitHub Actions)

A typical bi-weekly freeze workflow: generate a fresh report, then diff it against the previous one and post the summary to Slack.

```yaml
- name: Freeze report
  run: |
    TODAY=$(date +%Y-%m-%d)
    PREV_REPORT=$(ls -d freeze-reports/*/freeze.json 2>/dev/null | sort | tail -1)

    gradle-deps-monitor check gradle --out freeze-reports/$TODAY

    if [ -n "$PREV_REPORT" ]; then
      gradle-deps-monitor diff freeze-reports/$TODAY/freeze.json \
        --prev "$PREV_REPORT" \
        --out freeze-reports/$TODAY
    else
      gradle-deps-monitor diff freeze-reports/$TODAY/freeze.json \
        --out freeze-reports/$TODAY
    fi
  env:
    GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

Post the generated `freeze-slack.json` and `freeze-diff-slack.json` to your channel with any Slack webhook step.

---

## Project structure

```
src/gradle_deps_monitor/
├── domain/          # Entities, value objects, and per-section severities;
│                    #   severity_style.py provides unified rendering constants
├── application/     # Use cases (GenerateFreezeReport, ComputeFreezeDiff)
│                    #   and port interfaces
├── checks/          # Catalog health rules (pluggable)
├── infrastructure/  # TOML parser, HTTP registry clients, writers, cache
├── presentation/    # CLI commands, Rich console
├── bootstrap.py     # Composition root (wires everything together)
└── cli.py           # Typer entry point
```

The architecture follows [ADR-0006](docs/adr/0006-pragmatic-clean-architecture.md) (Pragmatic Clean Architecture with import-linter enforcement).

---

## Development

```bash
# Lint + format
ruff check . && ruff format .

# Type check
mypy src/

# Layer enforcement
lint-imports

# Tests
pytest

# All at once (same as CI)
ruff check . && ruff format --check . && mypy src/ && lint-imports && pytest
```

---

## Roadmap

See [docs/roadmap.md](docs/roadmap.md).  
Phases 1–4 are fully shipped. The backlog now drives next steps: HTML export (RFC-0010) and freeze-history trend rendering, plus exploratory items.

---

## Contributing

See [docs/CONTRIBUTING-AI.md](docs/CONTRIBUTING-AI.md) for the AI-assisted development workflow used in this project.

---

## License

MIT — see [LICENSE](LICENSE).

---

## Acknowledgements

This project started from an early prototype by [Paul Ayala](https://github.com/pfranccino) that proved the concept was worth pursuing. The current architecture and implementation are a full rewrite.
