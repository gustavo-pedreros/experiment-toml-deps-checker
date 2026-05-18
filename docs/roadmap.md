# Roadmap

This roadmap captures the multi-phase plan for evolving the tool from
its current state (a Bash + Python script that compares dependency
versions) into a comprehensive freeze-time technical due-diligence
report for Android/Gradle projects.

The plan is grouped into phases. Phases are sequential by default, but
individual items inside a phase may be reordered or shipped
independently.

Each item links to a proposal (RFC) when one exists. Decisions that
have already been made and that constrain implementation are recorded
as ADRs.

## Status legend

- 📋 **Planned** — accepted into the roadmap, not yet started
- 🚧 **In progress** — actively being built
- ✅ **Shipped** — merged and released
- 💭 **Exploring** — under discussion, may or may not be picked up
- ❌ **Rejected** — considered and declined (with rationale in the proposal)

## Phase 1 — Foundation

The technical baseline that everything else depends on. The
overall shape of this phase is constrained by [ADR-0006](adr/0006-pragmatic-clean-architecture.md)
(Clean Architecture) and [ADR-0007](adr/0007-tooling-stack.md)
(tooling stack).

| Status | Item | Reference |
|--------|------|-----------|
| ✅ | Project skeleton (`pyproject.toml`, `src/` layout, CI, import-linter) | [ADR-0006](adr/0006-pragmatic-clean-architecture.md), [ADR-0007](adr/0007-tooling-stack.md) |
| ✅ | Drop the Bash wrapper, move to a single Python entry point | [ADR-0001](adr/0001-python-over-bash.md) |
| ✅ | Robust TOML parsing (inline versions, `[plugins]`, `[bundles]`) | — |
| ✅ | Parallel HTTP requests via `httpx` async | — |
| ✅ | On-disk cache with TTL | — |
| ✅ | Markdown + JSON outputs, committable to `freeze-reports/` | [ADR-0002](adr/0002-markdown-as-canonical-output-format.md) |
| ✅ | Slack Block Kit output | — |
| ✅ | Console executive summary | — |
| ✅ | JSON output schema versioned (`schema_version: "x.y.z"` SemVer string) | [ADR-0008](adr/0008-json-schema-semver.md) |
| ✅ | Catalog Health audit (pluggable rules) | [RFC-0011](proposals/0011-catalog-health-audit.md) |

## Phase 2 — High-impact features for freeze workflow

Features that materially change the value of a freeze report.

| Status | Item | Reference |
|--------|------|-----------|
| ✅ | CVE scan via GitHub Advisory Database + OSS Index | [RFC-0001](proposals/0001-cve-scan.md) |
| ✅ | Play Store compliance check | [RFC-0002](proposals/0002-play-store-compliance.md) |
| ✅ | Diff between freezes (with first-run handling) | [RFC-0003](proposals/0003-freeze-diff.md) |
| ✅ | Changelog scraper for major upgrades | [RFC-0004](proposals/0004-changelog-scraper.md) |

## Phase 3 — Differentiating features

Features that move the tool from "useful" to "category-defining" for
Android teams at scale.

| Status | Item | Reference |
|--------|------|-----------|
| ✅ | Toolchain compatibility matrix (Kotlin / Compose / AGP / KSP / Hilt) | [RFC-0005](proposals/0005-toolchain-compatibility-matrix.md) |
| ✅ | Library health & deprecation prediction (hybrid KB + POM relocation) | [RFC-0006](proposals/0006-library-health-and-deprecation.md) |
| ✅ | Module usage map (opt-in, expensive but high-signal) | [RFC-0007](proposals/0007-module-usage-map.md) |

## Phase 4 — Polish and consolidation ✅ Closed (2026-05-07)

Phase 4 closed the gaps discovered while integrating Phases 1–3
end-to-end: dead infrastructure adapters, hard-coded config, BoM
families treated as independent libraries, the empty compliance
dimension in the risk score, and the visual inconsistency across
sections. All seven items shipped.

| Status | Item | Reference |
|--------|------|-----------|
| ✅ | Risk score (opt-in, transparent breakdown, configurable weights) | [RFC-0008](proposals/0008-risk-score.md) |
| ✅ | License audit | [RFC-0009](proposals/0009-license-audit.md) |
| ✅ | Layered configuration (`gradle-deps-monitor.toml`) | [RFC-0012](proposals/0012-layered-configuration.md) |
| ✅ | Version status as first-class data | [RFC-0013](proposals/0013-version-status-first-class.md) |
| ✅ | Maven BoM (Bill of Materials) support | [RFC-0014](proposals/0014-maven-bom-support.md) |
| ✅ | Compliance per-library attribution | [RFC-0015](proposals/0015-compliance-per-library-attribution.md) |
| ✅ | Unified report style (severity + row layout) | [RFC-0016](proposals/0016-unified-report-style.md) |

## Phase 5 — Scale & CI Integration 🚧 In progress

Focuses on making the tool production-ready for large Android teams,
improving audit visibility through CSV exports, and establishing
policy enforcement for CI/CD.

| Status | Item | Reference |
|--------|------|-----------|
| 🚧 | Comprehensive CSV Export (Inventory & Findings) | [RFC-0017](proposals/0017-csv-export.md) |
| 📋 | Official User Guide (English) | [RFC-0021](proposals/0021-user-guide.md) |
| ✅ | High-Performance & Accurate Module Scanner | [RFC-0019](proposals/0019-module-scanner.md) |
| ✅ | Robust Version Detection (Rich Versions) | [RFC-0020](proposals/0020-rich-versions.md) |
| 📋 | CI Gatekeeper (Policy Enforcement) | [RFC-0018](proposals/0018-ci-gatekeeper.md) |

## Phase 6 — Real-world stress test follow-ups 🚧 In progress

Findings surfaced while running the tool end-to-end against real
multi-module Android projects. Each item is a narrow bug fix or UX
improvement that materially changes report quality but doesn't
merit its own feature phase.

| Status | Item | Reference |
|--------|------|-----------|
| ✅ | Module Scanner — Accessor Coverage Follow-up (underscore aliases + `platform()` BoMs) | [RFC-0022](proposals/0022-module-scanner-accessor-coverage.md) |
| ✅ | License Classifier — GPL with Classpath Exception | [RFC-0023](proposals/0023-license-classpath-exception.md) |
| ✅ | Async Vulnerability Scanners + Changelog Scraper Observability | [RFC-0024](proposals/0024-async-scanners-scraper-observability.md) |
| ✅ | Parallel Orchestration of Independent Adapter Stages | [RFC-0025](proposals/0025-parallel-use-case-orchestration.md) |
| 🚧 | `PRE_1_0` Stability Tier for `0.x.y` Versions | [RFC-0026](proposals/0026-pre-1-0-stability-tier.md) |

## Backlog

Items accepted into the roadmap, scheduled after Phase 6.
Ordering inside the backlog is not yet fixed; items here may be
re-promoted into a later phase or split into sub-RFCs.

| Status | Item | Reference |
|--------|------|-----------|
| 📋 | HTML export (incorporates risk & freeze trend rendering) | [RFC-0010](proposals/0010-html-export.md) |
| 💭 | Tag annotation auto-generation | — |
| 💭 | Trend dashboard across freeze history | — |

## Cross-cutting infrastructure

Concerns that span all phases.

- Layered configuration (`gradle-deps-monitor.toml` + per-project
  overrides) — promoted to Phase 4 as
  [RFC-0012](proposals/0012-layered-configuration.md)
- CI test suite with real `libs.versions.toml` fixtures
- `docs/adr/` for accepted decisions
- `docs/proposals/` for pending proposals
- Pluggable rules architecture for catalog health and deprecation checks
- English as the canonical language for all repo content (see [ADR-0005](adr/0005-language-convention-english-in-repo.md))

## Decisions made

See [docs/adr/](adr/) for the full list of accepted architectural
decisions. The most consequential ones for newcomers:

- [ADR-0001](adr/0001-python-over-bash.md) — Python as the single language
- [ADR-0002](adr/0002-markdown-as-canonical-output-format.md) — Markdown as the canonical report format
- [ADR-0003](adr/0003-bundled-plus-remote-deprecation-kb.md) — How the deprecation knowledge base is distributed
- [ADR-0004](adr/0004-risk-score-opt-in-with-disclaimer.md) — Risk score is opt-in by default
- [ADR-0005](adr/0005-language-convention-english-in-repo.md) — All repo content is in English
- [ADR-0006](adr/0006-pragmatic-clean-architecture.md) — Pragmatic Clean Architecture for the Python CLI
- [ADR-0007](adr/0007-tooling-stack.md) — Tooling stack
- [ADR-0008](adr/0008-json-schema-semver.md) — JSON output `schema_version` follows SemVer (`x.y.z`)

## How to evolve this roadmap

- New ideas start as proposals in `docs/proposals/` (see the
  [template](proposals/README.md))
- A proposal moves into a phase here once it is accepted
- Items can be reordered or moved between phases as priorities shift
- Rejected items are kept (with status updated) so the rationale is
  preserved for the future
