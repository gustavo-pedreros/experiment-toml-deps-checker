# Changelog

All notable changes to this project will be documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project does not yet follow Semantic Versioning — version numbers will
be assigned once a stable public API is established.

---

## [Unreleased]

### Fixed
- Parser no longer crashes on Gradle Version Catalogs that use rich-version
  blocks (`strictly` / `require` / `prefer` / `reject`). Previously,
  `TomlCatalogParser` raised `CatalogParseError` on the first such entry,
  making the tool unusable for teams pinning toolchains via `strictly`
  (a common pattern with Kotlin / KSP / AGP). See
  [RFC-0020](docs/proposals/0020-rich-versions.md) — Tracer Bullet.
- Parser now also accepts rich-version blocks in the top-level `[versions]`
  table (e.g. `kotlin = { strictly = "2.0.0" }`), not only inline on
  `[libraries]` / `[plugins]` entries. Previously the tracer fix only
  covered library-level rich blocks; catalogs pinning Kotlin/KSP/AGP via
  `[versions]` + `version.ref` still crashed at parse time. Rich blocks
  in `[versions]` are flattened to their effective string in
  `Catalog.versions`, preserving the `dict[str, str]` contract for
  downstream consumers. RFC-0020 — PR #2.
- `ToolchainCompatibilityChecker` now sees Kotlin/AGP/KSP versions that
  are declared with rich blocks in `[versions]`. Before, the checker
  silently skipped non-string entries because it re-parsed the raw TOML
  itself, so pinning Kotlin with `strictly` made the entire toolchain
  audit invisible.

### Changed
- `ToolchainCompatibilityChecker` no longer re-parses the catalog TOML
  file. It consumes `Catalog.versions` directly, per the RFC-0020 checker
  contract ("checkers stop doing any TOML-aware introspection"). Behaviour
  is unchanged for catalogs that use plain-string versions.

### Added
- New `RichVersion` domain value object capturing the four Gradle rich-version
  keys plus a derived `effective` version (precedence: `strictly` > `require`
  > `prefer`, falling back to an empty version for reject-only entries).
- `Library.version_constraints` optional field, set only when the catalog
  actually uses a rich block. Construction is guarded by a runtime invariant:
  `version_constraints.effective` must equal `version`.
- `freeze.json` schema bumped to `1.5.0` (MINOR per ADR-0008). Adds optional
  `version_constraints` per library entry. Existing consumers reading `1.x`
  continue to work.
- Production-style fixture under `tests/fixtures/rich_versions/` covering
  Kotlin/KSP `strictly`, AGP `require`, Hilt `prefer`, Coil `reject`-only,
  plus plain-string and `version.ref` libraries in the same catalog.
- New **Active Rejections** section in the Markdown report. Lists every
  library whose catalog entry declares a `reject` list — intentional
  negative pins (often known-vulnerable releases) — so reviewers see them
  in one place. Emits nothing when no library uses `reject`. The JSON
  report already exposes the same data per library since schema 1.5.0.

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
