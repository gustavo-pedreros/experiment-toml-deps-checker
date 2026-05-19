# Proposals (RFCs)

This folder holds proposals for changes to the tool that have not yet
been accepted as part of the implementation plan. Each proposal is a
short document that frames a problem, a proposed solution, and the
considered alternatives.

Proposals are how new ideas enter the project. Anyone may write one.

## Lifecycle

A proposal moves through these states:

- **Proposed** — written and submitted, awaiting review
- **Exploring** — under active discussion, may evolve
- **Accepted** — merged into the roadmap, ready to be picked up
- **In progress** — being implemented
- **Shipped** — merged and released
- **Rejected** — declined, with rationale captured

Rejected proposals are kept in this folder. They preserve the
historical record of what was considered and why something was not
done.

## Template

```markdown
# RFC-NNNN: Short title

**Status:** Proposed
**Author:** @your-handle
**Created:** YYYY-MM-DD
**Related JTBDs:** JTBD-N (see docs/jtbd.md)
**Depends on:** RFC-XXXX (or `none`)

## Problem

What is the user-facing problem? What gap or pain motivates this
change? Avoid jumping to a solution.

## Proposed solution

How would the tool behave once this is implemented? What does the
user see? What does the report look like?

Where helpful, include a concrete output example.

## Tracer Bullet Path (ADR-0009)

Describe the thinnest end-to-end path to see a real data point in the final report.
Identify what needs to be wired in the **Composition Root** (e.g., `bootstrap.py`) for the first PR.

## Alternatives considered

What other approaches were considered? Why were they not chosen?

## Cost estimate

Rough effort: small / medium / large. Any new dependencies, external
APIs, or operational concerns.

## Success metrics

How will we know this proposal achieved its goal once shipped?

## Schema impact

Declare any change to `freeze.json` / `freeze-diff.json` schema per
ADR-0008: `none | patch | minor | major`. If the change adds an output
file (CSV, HTML, etc.) describe its versioning contract here too.

## Rollback strategy

How can this change be reverted without breaking downstream consumers?
Required for any RFC that adds an output file, changes a schema, or
introduces a new CLI flag that other tooling may come to depend on.
List the revert order if multiple PRs are involved.

## PR budget

Estimated number of PRs from tracer to DoD. If `> 5`, consider
splitting into sub-RFCs.

## Definition of Done (DoD)

- [ ] **Integration**: Wired in the **Composition Root** and visible in at least one report output.
- [ ] **Architecture**: Follows ADR-0006 (Clean Architecture) and ADR-0009 (Tracer Bullets).
- [ ] **Testing**: Integration tests cover the Tracer Bullet path.
- [ ] **Documentation**: README or User Guide updated if applicable.
```

## Index

| ID | Title | Status | JTBDs |
|----|-------|--------|-------|
| [0001](0001-cve-scan.md) | CVE scan via GitHub Advisory Database and OSS Index | Proposed | 2 |
| [0002](0002-play-store-compliance.md) | Play Store compliance check | Proposed | 1 |
| [0003](0003-freeze-diff.md) | Diff between freeze reports | Proposed | 5 |
| [0004](0004-changelog-scraper.md) | Changelog scraping for major upgrades | Proposed | 6 |
| [0005](0005-toolchain-compatibility-matrix.md) | Toolchain compatibility matrix | Proposed | 4 |
| [0006](0006-library-health-and-deprecation.md) | Library health and deprecation prediction | Proposed | 3 |
| [0007](0007-module-usage-map.md) | Module usage map | Proposed | 6 |
| [0008](0008-risk-score.md) | Risk score | Proposed | 6 |
| [0009](0009-license-audit.md) | License audit | Proposed | 2 |
| [0010](0010-html-export.md) | HTML export | Proposed | 5 |
| [0011](0011-catalog-health-audit.md) | Catalog health audit | Proposed | 3 |
| [0012](0012-layered-configuration.md) | Layered configuration (`gradle-deps-monitor.toml`) | Proposed | cross-cutting |
| [0013](0013-version-status-first-class.md) | Version status as first-class data | Proposed | 1, 6 |
| [0014](0014-maven-bom-support.md) | Maven BoM (Bill of Materials) support | Proposed | 1, 3, 6 |
| [0015](0015-compliance-per-library-attribution.md) | Compliance per-library attribution | Proposed | 2, 6 |
| [0016](0016-unified-report-style.md) | Unified report style (severity + row layout) | Proposed | 5 |
| [0017](0017-csv-export.md) | Comprehensive CSV Export (Inventory & Findings) | Proposed | 5 |
| [0018](0018-ci-gatekeeper.md) | CI Gatekeeper (Policy Enforcement) | Proposed | 1, 2 |
| [0019](0019-module-scanner.md) | High-Performance & Accurate Module Scanner | Proposed | 3, 5 |
| [0020](0020-rich-versions.md) | Robust Version Detection (Rich Versions Support) | Proposed | 5 |
| [0021](0021-user-guide.md) | Official User Guide | Proposed | 5 |
| [0022](0022-module-scanner-accessor-coverage.md) | Module Scanner — Accessor Coverage Follow-up (underscore aliases + `platform()` BoMs) | Proposed | 3, 5 |
| [0023](0023-license-classpath-exception.md) | License Classifier — GPL with Classpath Exception | Proposed | 2, 5 |
| [0024](0024-async-scanners-scraper-observability.md) | Async Vulnerability Scanners + Changelog Scraper Observability | Proposed | 5, 6 |
| [0025](0025-parallel-use-case-orchestration.md) | Parallel Orchestration of Independent Adapter Stages | Proposed | 5, 6 |
| [0026](0026-pre-1-0-stability-tier.md) | `PRE_1_0` Stability Tier for `0.x.y` Versions | Proposed | 1, 5 |
| [0027](0027-version-registry-stability-gate.md) | Stability-Gated `<release>` Fallback in Version Registries | Proposed | 1, 5 |
| [0028](0028-phase6-wrap-up-empty-sections-and-console-buckets.md) | Phase 6 Wrap-up — Render Empty Sections + Fix Console Severity Buckets | Proposed | 1, 5 |
| [0029](0029-cache-controls.md) | Cache controls (CLI flags, per-source TTL, env-var root) | Proposed | 5 |
| [0030](0030-http-resilience.md) | Shared HTTP resilience layer (retry / backoff / Retry-After) | Proposed | 5 |
| [0031](0031-bootstrap-composition-tests.md) | Bootstrap composition-root unit tests | Proposed | 5 |
| [0032](0032-atomic-writes.md) | Atomic report writes (temp-file + os.replace) | Proposed | 3, 5 |
| [0033](0033-analyze-freeze-skill.md) | `/analyze-freeze` skill and canonical query library | Proposed | 3, 5 |
| [0034](0034-output-slack-opt-in.md) | Slack output becomes opt-in (`--slack` flag + `[output]` config) | Proposed | 3, 5 |

> Lifecycle status (Accepted, In progress, Shipped) is tracked in
> [`docs/roadmap.md`](../roadmap.md). The "Status" column above
> reflects the state at authoring time.
