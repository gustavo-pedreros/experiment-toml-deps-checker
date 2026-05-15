# ADR-0003: Bundled-plus-remote distribution for the deprecation knowledge base

## Status

Accepted — 2026-05-03

## Context

The deprecation prediction feature (see [RFC-0006](../proposals/0006-library-health-and-deprecation.md))
relies on a curated knowledge base of known deprecation paths in the
Android ecosystem (e.g., `butterknife → ViewBinding`, `kapt → KSP`,
`com.android.support.* → androidx.*`).

Three distribution models were considered:

- **Bundled only**: ship the knowledge base as a file inside the
  Python package. Updates require a new tool release. Predictable
  and offline-friendly, but slow to react to ecosystem changes.
- **Remote only**: fetch from a canonical URL on every run.
  Always current, but breaks in offline environments and depends on
  uptime of the hosting infrastructure.
- **Hybrid**: ship a bundled copy as fallback, fetch a remote copy
  when available, and allow the user to override locally.

In addition to the curated list, two automatic detection sources
were identified:

- **Maven POM `<relocation>` tags**: the official mechanism for
  declaring an artifact has moved. When present, this is 100%
  reliable and requires no curation.
- **Android Jetpack migration tables**: published by Google,
  mapping `com.android.support.*` to `androidx.*`.

## Decision

The deprecation knowledge base is distributed using the **hybrid
model**, with three layers of precedence:

1. **Bundled copy** (`data/deprecations.yaml`) — shipped with every
   tool release. Always available, including offline.
2. **Remote copy** — fetched from the tool's GitHub repository (raw
   URL) once per configured TTL (default: 7 days), with HTTP ETag
   for efficient revalidation. Cached on disk under
   `~/.cache/gradle-deps-monitor/`.
3. **Local override** — a project-level YAML file (e.g.,
   `.deprecations.local.yaml`) where teams can add internal
   deprecations or override entries.

Automatic detection sources (POM relocation tags, Jetpack migration
tables) run alongside the curated knowledge base and contribute
findings independently. Their results are tagged in the report so
the source of each finding is transparent.

A `--refresh-kb` flag forces an immediate remote fetch, useful
between scheduled refreshes.

## Consequences

**Positive**

- Works offline thanks to the bundled fallback
- Stays current without requiring users to upgrade the tool
- Allows teams to extend the knowledge base for their own
  deprecations without forking
- Multiple data sources increase coverage; the curated list is no
  longer the single point of truth

**Negative**

- Three layers of resolution introduce some complexity in the
  loader and require clear precedence rules
- The remote copy is a new operational dependency — its hosting
  must be stable. Hosting on the same GitHub repo (raw content)
  minimizes this risk.
- Cache invalidation must be handled carefully; ETag is the
  primary mechanism, with TTL as a fallback
