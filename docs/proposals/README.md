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

## Alternatives considered

What other approaches were considered? Why were they not chosen?

## Cost estimate

Rough effort: small / medium / large. Any new dependencies, external
APIs, or operational concerns.

## Success metrics

How will we know this proposal achieved its goal once shipped?
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
