# gradle-deps-monitor

**Freeze-time technical due-diligence report for Android / Gradle projects.**

Analyses a `libs.versions.toml` version catalog, checks every dependency against Maven Central and Google Maven, audits catalog health, scans for CVEs, validates Play Store compliance, checks toolchain compatibility, and writes structured reports — Markdown, JSON, and Slack Block Kit — ready to commit or post automatically via CI.

---

## Features

- **Version status** — compares pinned versions against the latest release on Maven Central / Google Maven, flagging stable, release-candidate, beta, alpha, and dev versions
- **Catalog health audit** — 8 pluggable rules that surface structural problems: duplicate libraries, unresolved `version.ref` keys, orphan version entries, inconsistent alias naming, missing plugins/bundles, and more
- **CVE scan** — queries GitHub Advisory Database and OSS Index for known vulnerabilities in every pinned library (requires `GITHUB_TOKEN` / `OSSINDEX_USER` + `OSSINDEX_API_KEY`)
- **Play Store compliance** — detects deprecated libraries (e.g. SafetyNet → Play Integrity) and checks `targetSdk` against Google's published requirements
- **Toolchain compatibility** — validates Kotlin ↔ Compose Compiler, Kotlin ↔ KSP, and AGP ↔ Gradle against bundled compatibility matrices; catches mismatches before they reach QA
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

---

## Output

### Console

```
╭─ Gradle Dependency Freeze Report ─╮
│ Generated  2026-05-04T10:00:00    │
│ Libraries  42                      │
│ Plugins    6                       │
│ Bundles    3                       │
╰────────────────────────────────────╯

Catalog Health — no issues found

Reports written → freeze-reports/2026-05-04
  • freeze.md
  • freeze.json
  • freeze-slack.json
```

### Files written

| File | Format | Purpose |
|------|--------|---------|
| `freeze.md` | Markdown | Human-readable report; commit to `freeze-reports/` |
| `freeze.json` | JSON (`schema_version: 1`) | CI parsing, dashboards |
| `freeze-slack.json` | Slack Block Kit | Post via incoming webhook |

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

---

## Toolchain compatibility rules

Validated automatically on every run. No credentials required.

| Rule ID | Check | How it works |
|---------|-------|-------------|
| `TOOL-KC-001` | Kotlin ↔ Compose Compiler | Kotlin 2.x: must match exactly. Kotlin 1.x: looked up in the bundled `kotlin-compose.yaml` matrix |
| `TOOL-KSP-001` | Kotlin ↔ KSP | KSP version must start with the Kotlin version prefix (e.g. `2.1.10-1.0.29` for Kotlin `2.1.10`) |
| `TOOL-AGP-001` | AGP ↔ Gradle wrapper | Gradle version is read from `gradle/wrapper/gradle-wrapper.properties` and compared against the `agp-gradle.yaml` matrix |

The bundled matrices cover Kotlin 1.7–2.x, AGP 7.0–8.9, and all published KSP releases. Matrix files live in `src/gradle_deps_monitor/data/compatibility/` and can be updated via PR as new toolchain versions are released.

---

## CI integration (Bitrise / GitHub Actions)

```yaml
- name: Freeze report
  run: |
    gradle-deps-monitor check gradle --out freeze-reports/$(date +%Y-%m-%d)
```

Post the generated `freeze-slack.json` to your channel with any Slack webhook step.

---

## Project structure

```
src/gradle_deps_monitor/
├── domain/          # Core entities: Catalog, Library, Plugin, MavenVersion, Finding
├── application/     # Use cases and port interfaces
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
Phase 1 (foundation) and Phase 2 (CVE scan, Play Store compliance, freeze diff) are complete. Phase 3 is in progress with the toolchain compatibility matrix (RFC-0005).

---

## Contributing

See [docs/CONTRIBUTING-AI.md](docs/CONTRIBUTING-AI.md) for the AI-assisted development workflow used in this project.

---

## License

MIT — see [LICENSE](LICENSE).

---

## Acknowledgements

This project started from an early prototype by [Paul Ayala](https://github.com/pfranccino) that proved the concept was worth pursuing. The current architecture and implementation are a full rewrite.
