# Jobs To Be Done

This document captures the underlying user goals the tool exists to
serve. Features are evaluated by how well they address one or more of
these jobs.

The tool is most often invoked at **freeze time**: a periodic
checkpoint (e.g., every two weeks) where a release candidate is
prepared for QA. The freeze report becomes both an antecedent for the
next development cycle and an audit trail for the release that just
shipped.

## Primary user

An Android engineering team using Gradle Version Catalogs
(`libs.versions.toml`) to manage shared dependencies across many
modules. The team:

- Periodically freezes a release candidate for QA / regression / fixes
- Wants a snapshot of dependency state at the freeze moment
- Uses the snapshot to plan technical work for the next cycle
- May operate in a regulated context (fintech, health, payments) where
  vulnerabilities and license risks have business consequences

## The jobs

### JTBD-1 — Compliance

> "Am I compliant with what Google Play and other platforms require to
> publish or update this app?"

The tool surfaces:
- Target SDK requirements (current minimum, upcoming deadlines)
- 64-bit ABI compliance
- App Bundle (AAB) format requirements
- Deprecated SDKs still in use (e.g., SafetyNet → Play Integrity)
- Other platform-driven deadlines

### JTBD-2 — Security risk

> "What known vulnerabilities am I shipping in this release?"

For regulated industries this is non-negotiable. The tool surfaces:
- CVEs by severity for each dependency
- Whether a fixed version is available
- Whether a critical vulnerability is reachable from the app's code
  (advanced, future)

### JTBD-3 — Technical debt to plan

> "How much upgrade work is waiting for me in the next cycle?"

The tool surfaces:
- Outdated dependencies grouped by major / minor / patch gap
- Abandoned or maintenance-mode libraries
- Libraries with known successors (deprecation paths)

### JTBD-4 — Cross-cutting compatibility

> "Is my Kotlin / Compose / AGP / KSP / Hilt stack internally
> consistent?"

These libraries are coupled by official compatibility matrices.
Breaking these matrices breaks builds in subtle ways. The tool
surfaces:
- Required version pairings
- Detected inconsistencies
- Recommended upgrades when one component moves

### JTBD-5 — Traceability across freezes

> "What changed since the last freeze?"

Each freeze becomes a comparable data point. The tool surfaces:
- Dependencies upgraded / added / removed
- New CVEs introduced (or resolved)
- Compliance status changes
- Risk trend across multiple freezes

When no previous freeze exists, the current one establishes the
baseline.

### JTBD-6 — Informed upgrade decisions

> "Is upgrading X worth it now, or should I defer?"

The tool helps weigh the cost and risk of an upgrade by surfacing:
- A transparent risk score combining several dimensions
- Blast radius (how many modules use this dependency)
- Breaking changes (from changelog scraping)
- License implications

## How features map to jobs

| Feature | JTBD |
|---------|------|
| Markdown / JSON output committed to `freeze-reports/` | 5 |
| Slack Block Kit output | 1, 2, 3 |
| Catalog health audit | 3 |
| CVE scan | 2 |
| Play Store compliance check | 1 |
| Freeze diff | 5 |
| Changelog scraper | 6 |
| Toolchain compatibility matrix | 4 |
| Library health & deprecation prediction | 3 |
| Module usage map | 6 |
| Risk score | 6 |
| License audit | 2 |
