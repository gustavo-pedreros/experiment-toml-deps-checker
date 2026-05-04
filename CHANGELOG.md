# Changelog

All notable changes to this project will be documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project does not yet follow Semantic Versioning — version numbers will
be assigned once a stable public API is established.

---

## [Unreleased]

---

## [0.1.0] — 2026-05-04

First complete release of Phase 1 — the technical foundation.

### Added

#### Project skeleton (Step 1–2)
- `pyproject.toml` with Hatchling build backend, `src/` layout, and `gradle-deps-monitor` CLI entry point
- Pragmatic Clean Architecture layer structure: `domain`, `application`, `checks`, `infrastructure`, `presentation`, `bootstrap`
- `import-linter` with 5 enforced contracts preventing cross-layer coupling
- CI workflow (GitHub Actions): ruff, mypy, import-linter, pytest
- ADRs 0001–0007 documenting all key architectural decisions
- Proposals 0001–0011 capturing the full feature roadmap

#### Domain model (Step 2)
- `MavenVersion` — parses Maven version strings, classifies stability (stable / RC / beta / alpha / dev), supports comparison
- `Library` and `Plugin` — frozen dataclasses with `version_ref` tracking
- `Catalog` — frozen dataclass with `library_count`, `plugin_count`, and raw `versions` map
- `FreezeReport` — top-level aggregate combining catalog + HTTP results + health findings

#### TOML parser (Step 3)
- `TomlCatalogParser` — parses `libs.versions.toml` including `[versions]`, `[libraries]`, `[plugins]`, `[bundles]`; resolves `version.ref` to concrete version strings; propagates `version_ref` alias to domain objects

#### HTTP registry + cache (Steps 4–5)
- Async `httpx` clients for Maven Central and Google Maven
- `diskcache`-backed on-disk cache with configurable TTL
- `MavenCentralRegistry` and `GoogleMavenRegistry` — query latest available version per artifact
- Parallel async resolution of all catalog entries

#### Writers (Step 6)
- `MarkdownWriter` — human-readable freeze report with per-library status table and non-stable version highlights
- `JsonWriter` — machine-readable output, `schema_version: 1`, fully typed

#### CLI + bootstrap (Step 7)
- `typer`-based CLI with `check` sub-command and `--out` / `-o` option
- `bootstrap.py` as the sole composition root — wires parser, use case, and writers
- `--version` flag

#### Catalog health audit (Step 8)
- `Finding` domain object with `rule_id`, `Severity` (`error` / `warning` / `info` / `suggestion`), `message`, and `details`
- `HealthChecker` Protocol — callable interface satisfied by `run_all`
- 8 health rules:
  - `HDX-001` (error) — duplicate library (`group:artifact` declared more than once)
  - `HDX-002` (error) — unresolved `version.ref` (missing key in `[versions]`)
  - `HDX-003` (warning) — inconsistent alias naming (camelCase / kebab-case mix)
  - `HDX-004` (warning) — no `[plugins]` block in a non-empty catalog
  - `HDX-005` (warning) — orphan version key (declared but never referenced)
  - `HDX-006` (info) — inline version literals (prefer `version.ref`)
  - `HDX-007` (info) — no `[bundles]` block
  - `HDX-008` (suggestion) — duplicate version values (different keys, same string)

#### Slack + console output (Steps 9–10)
- `SlackWriter` — Slack Block Kit JSON: header, meta (timestamp + catalog name), stats with stable/non-stable breakdown, non-stable versions list (truncated at 10), health findings
- `print_summary()` — Rich `Panel`-based console executive summary with colour-coded severity and written-file list
- `CheckCommand.run()` returns `(report, written_files)` tuple so the CLI can display exact output paths

### Changed
- `GenerateFreezeReport` use case extended to accept an optional `HealthChecker` and populate `FreezeReport.health_findings`

### Removed
- Legacy Bash wrapper (`check-dependencies.sh`) and original Python script (`version-stats.py`) — superseded by the new CLI

---

[Unreleased]: https://github.com/gustavo-pedreros/toml-deps-checker/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/gustavo-pedreros/toml-deps-checker/releases/tag/v0.1.0
