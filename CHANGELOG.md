# Changelog

All notable changes to this project will be documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project does not yet follow Semantic Versioning — version numbers will
be assigned once a stable public API is established.

---

## [Unreleased]

### Added
- `ChangelogFetcher` now tracks per-library outcomes during scraping
  and returns a new `ChangelogFetchStats` alongside the entries
  (attempted / fetched / fallback_url_only / rate_limited /
  unknown_no_repo counters). Both the console summary and the
  Markdown report's **Major Upgrades** section render an explicit
  warning when `rate_limited > 0`, pointing the user at the
  `GITHUB_TOKEN` mitigation. Pre-fix the scraper degraded silently
  under the 60 req/h unauthenticated GitHub limit — affected
  libraries flipped from `BREAKING`/`CLEAN` (with full release-note
  URLs) to `UNKNOWN` (with bare repo URLs) between runs with no
  signal in the report that data quality had dropped. RFC-0024 PR #2.
- `freeze.json` schema bumped to `1.6.0` (MINOR per ADR-0008). Adds
  optional `changelog_stats` object under `major_upgrades` with the
  five counters above. Consumers reading `1.x` continue to work; the
  new field is always present (default zeros when no scraping ran).

### Fixed
- `LibraryHealthChecker` no longer false-flags **JSR / Jakarta EE
  reference implementations as abandoned**. Any library whose group is
  exactly `javax`, `jakarta`, or a sub-namespace of either now skips
  the inactivity heuristic — these specs are frozen by design, so a
  5,780-day-old `javax.inject:javax.inject` is a feature, not a
  signal. Issue #10 from the 2026-05 stress-test menu.
- `PomLicenseChecker` no longer echoes placeholder names like literal
  `LICENSE` / `LICENSE.txt` / `License` in the License Audit's name
  column. Such values carry no information and look broken in the
  report; they're now normalised to `None` at finding-construction
  time, so the writer renders the standard `_(not declared)_`
  placeholder instead. The classification still falls through to
  `UNKNOWN` (unchanged). Issue #11.
- `Library.is_bom_candidate` now recognises **release-line suffixed
  BoM artifacts** like `compose-bom-alpha` / `foo-platform-rc1`.
  Pre-fix the regex required an exact `-bom$` / `-platform$` ending,
  so Compose's alpha BoM line was silently treated as a regular
  library — module-usage already credited it (RFC-0022 PR fixed the
  scanner side), but the **BoMs** report section and downstream BoM
  enrichment skipped it. Issue #15.
- Console `Outdated (N)` summary now matches the Markdown report's
  total. Pre-fix the console count excluded libraries whose drift
  resolved to `UNKNOWN` (e.g. artifacts hosted on non-standard
  repositories), so the same run printed `Outdated (123)` in console
  vs `135 of 170` in Markdown. The breakdown line now also shows the
  unknown count when non-zero. Issue #12.
- Markdown `Outdated summary` now carries a one-line note explaining
  that the **Drift** column in the Libraries table targets the latest
  available version (including pre-releases), whereas the **Major
  Upgrades** section uses the latest stable major. Pre-fix the two
  could disagree silently — e.g. an artifact pinned at 8.13.2 showing
  `→ 9.3.0-alpha05` in Libraries vs `→ 9.2.1` in Major Upgrades — and
  the reader had no way to tell which to trust. Issue #9.
- `PomLicenseChecker` no longer false-positives on **GPL with
  Classpath Exception (CPE)**. The classifier now detects the
  qualifier (`"classpath exception"` / `"with classpath"` /
  `"classpath-exception"`) before the GPL keyword cascade fires and
  downgrades the result to `PERMISSIVE` — which is what the exception
  is designed to be for application linking. Pre-fix, libraries like
  `com.android.tools:desugar_jdk_libs` (Google's mandatory desugaring
  library for projects targeting API < 26) were flagged as 🔴 Strong
  Copyleft, suggesting they had to be removed. The fix mirrors the
  existing LGPL-before-GPL precedence already in place. RFC-0023.
- `GradleModuleScanner` now matches catalog aliases that use only
  underscores (e.g. `internal_sdk_android`) against the dotted
  accessors build files actually reference (`libs.internal.sdk.android`).
  Pre-fix, the alias normaliser only handled `-` → `.`, so projects
  with underscore-only aliases had every reference silently dropped
  from the module usage map. When the affected libraries also carried
  CVEs, the risk score's blast-radius dimension reported `0/15 "not
  used"` — actively understating security risk. RFC-0022.
- `GradleModuleScanner` now detects Maven BoM applications wrapped in
  `platform()`, `enforcedPlatform()`, and `testFixtures()`. Pre-fix,
  the regex required `libs.` immediately after the configuration
  keyword, so every `implementation platform(libs.x.bom)` declaration
  was invisible — BoMs reported `0` direct uses even when applied in
  many modules. The wrapper whitelist is intentionally narrow to
  avoid crediting arbitrary helper functions wrapping `libs.*`.
  RFC-0022.
- Markdown module usage section banner now enumerates every
  recognised accessor form (dotted, camelCase, bundle expansion, BoM
  wrapper) instead of the obsolete "only dotted-accessor form"
  wording carried over from the RFC-0019 tracer. RFC-0022.
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
- `GradleModuleScanner` now recognises **camelCase accessors**
  (`libs.androidxCoreKtx`) in addition to the dotted form
  (`libs.androidx.core.ktx`). The camelCase form is the canonical
  accessor in Kotlin DSL type-safe blocks, so KTS-heavy projects had
  their usage counts systematically under-reported pre-fix. RFC-0019
  PR #1.
- `GradleModuleScanner` now survives a single corrupt or unreadable
  `build.gradle(.kts)` file. Previously, `errors="replace"` silently
  substituted U+FFFD characters, hiding the corruption; the scanner
  now reads with `errors="strict"` and emits a `MOD-001` finding for
  the affected module while continuing the scan on the rest of the
  project. RFC-0019 PR #1.
- `GradleModuleScanner` now credits **bundle members** when a module
  declares `libs.bundles.<name>`. Previously, bundle usages were
  silently ignored — projects that organise their dependencies through
  the catalog's `[bundles]` section (common for Compose, networking,
  testing stacks) had every member library reported with zero usage.
  Both accessor forms are recognised: dotted (`libs.bundles.compose.ui`)
  and camelCase (`libs.bundles.composeUi`). A library referenced both
  directly and via a bundle in the same module is credited exactly
  once per configuration bucket. The module's `direct_dep_count`
  reflects the expanded set, matching how Gradle resolves the
  dependency graph at compile time. RFC-0019 PR #2.

### Changed
- `GenerateFreezeReport.execute` now orchestrates its independent
  adapter stages in parallel. The six adapters that consume the
  enriched catalog without depending on each other (vulnerability
  scanner, library health checker, changelog fetcher, module-usage
  scanner, license checker, version-status resolver) run concurrently
  via `asyncio.gather`; risk score still runs after them as it
  consumes their output. Pre-fix each stage was awaited before the
  next began, so wall-clock summed per-stage costs (5 s + 2 s + 2 s +
  0.5 s + 3 s + 3 s ≈ 15 s of HTTP-bound work serialised at the
  orchestration layer). Now wall-clock is dominated by the slowest
  individual adapter. No port signature change, no domain model
  change, no schema change — output is byte-identical to pre-RFC
  runs. RFC-0025.
- `GitHubAdvisoryScanner._scan_with` now runs per-library lookups in
  parallel with `asyncio.gather`, bounded to `_MAX_CONCURRENT_REQUESTS
  = 20` via an `asyncio.Semaphore`. Pre-fix the loop awaited each
  query before starting the next, costing 30-50 seconds of wall-clock
  on a cold cache for typical Android catalogs (measured: 39 s for 103
  libraries, 59 s for 170 libraries — both with a valid GitHub token).
  Output order matches input order (`gather` preserves submission
  order); no consumer of the scanner output sees any contract change.
  `OssIndexScanner` is unaffected — it already amortises per-library
  cost by batching up to 128 PURLs per POST. RFC-0024 PR #1.
- `GradleModuleScanner.scan` is now an `async def` coroutine. Per-module
  file reads + regex parsing run in parallel via `asyncio.to_thread`
  + `asyncio.gather`, so a 200-module project no longer pays a
  serialised read for every `build.gradle(.kts)`. Output and findings
  are identical to PR #2 (same accessors, same `MOD-001` semantics,
  same bundle attribution). RFC-0019 PR #3.
- `ModuleUsageScanner` port signature changed to `async def scan(...)`,
  matching the other six async adapter ports. Downstream impact:
  callers `await` the coroutine. The `GradleModuleScanner` is the only
  in-tree implementation; user-defined implementations need to convert
  their `def scan` to `async def scan`. This is a breaking change for
  third-party adapters but not for end users of the CLI.
- `GenerateFreezeReport.execute` is now an `async def` coroutine. The
  previous pattern of seven independent `asyncio.run(...)` calls inside
  the use case is replaced by a single `asyncio.run(...)` at the CLI
  entry (`CheckCommand.run`). Every adapter now shares one event loop
  and one default thread pool. Behaviour is unchanged for end users;
  callers that drove `execute` directly (custom integrations) need to
  `await` the coroutine or wrap it in `asyncio.run`. RFC-0019 PR #3.
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

[Unreleased]: https://github.com/gustavo-pedreros/experiment-toml-deps-checker/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/gustavo-pedreros/experiment-toml-deps-checker/releases/tag/v0.1.0
