# RFC-0013: Version status as first-class data

**Status:** Proposed
**Created:** 2026-05-06
**Related JTBDs:** JTBD-1 (know what is outdated), JTBD-6 (rank by risk)
**Depends on:** none directly; consumed by [RFC-0008](0008-risk-score.md)
and [RFC-0014](0014-maven-bom-support.md)

## Problem

Three issues conflate into the same gap:

1. **Dead code in `infrastructure/registries/`.**
   `MavenCentralRegistry` and `GoogleMavenRegistry` plus the
   `VersionRegistry` port exist but no use case wires them in.
   The `MavenMetadataRegistry` base class with its `diskcache`
   integration is unused.
2. **Duplicate maven-metadata.xml fetching.**
   `ChangelogFetcher._get_latest` reimplements metadata fetching;
   `LibraryHealthChecker` does its own variant for the inactivity
   heuristic. Both bypass the cached registry adapter.
3. **Risk score outdatedness only counts MAJOR drift.**
   [RFC-0008](0008-risk-score.md) explicitly documents
   `patch_diff → 0-5; minor_diff → 5-15; major_diff (1) → 15-20;
   major_diff (≥2) → 25`. The implementation reads from
   `changelog_entries`, which is only populated for major upgrades,
   so patch and minor drift score `0` silently.

The README's first feature bullet ("Version status — compares
pinned versions against the latest release on Maven Central /
Google Maven, flagging stable, RC, beta, alpha, dev") describes a
behaviour that does not exist at the report level. Stability of
the **pinned** version is detected, but the comparison to latest
is missing.

## Proposed solution

Introduce a per-library `LibraryVersionStatus` produced as a
first-class step in `GenerateFreezeReport`, fed by the existing
(but unused) registry adapters.

### Domain model

```python
class VersionDrift(StrEnum):
    NONE  = "none"   # pinned == latest
    PATCH = "patch"  # 1.2.3 → 1.2.4
    MINOR = "minor"  # 1.2.3 → 1.3.0
    MAJOR = "major"  # 1.2.3 → 2.0.0
    UNKNOWN = "unknown"  # latest not resolvable

@dataclass(frozen=True)
class LibraryVersionStatus:
    alias: str
    coordinate: str
    pinned: MavenVersion
    latest: MavenVersion | None
    drift: VersionDrift
```

### Use case integration

- `GenerateFreezeReport` resolves the latest stable version for
  every library in parallel using the existing
  `MavenCentralRegistry` and `GoogleMavenRegistry` adapters.
- Resolution order: try Google Maven first for `androidx.*` /
  `com.google.*` groups, Maven Central otherwise. Fall back to the
  other if the primary returns 404.
- `FreezeReport` gains
  `library_version_statuses: tuple[LibraryVersionStatus, ...]`.

### Risk score consumer

- `_score_outdatedness` switches its source from `changelog_by_alias`
  to `version_status_by_alias`. Patch/minor/major drift scores per
  RFC-0008's documented spec.

### Writers

- **Markdown**: an additional column "Drift" (`—`, `patch`, `minor`,
  `major`) in the libraries table; an "Outdated summary" line in
  the executive summary.
- **JSON**: each library entry gains
  `version_status: { latest, drift }`. Schema bumps to `1.1.0` per
  [ADR-0008](../adr/0008-json-schema-semver.md).
- **Slack**: footer counts ("4 libs major-behind, 7 minor-behind,
  12 patch-behind").
- **Console**: stays close to today's "Pre-release pinned" block,
  adds a "Outdated" block summarising counts.

### Refactor opportunities (optional in v1)

- `ChangelogFetcher` can drop its private metadata fetcher and
  consume the resolved `version_statuses` from the report — single
  shared cache, fewer HTTP calls, deterministic ordering.
- `LibraryHealthChecker`'s inactivity heuristic still needs the
  raw `<lastUpdated>` timestamp (not the latest stable), so it
  keeps its own fetch — but it can hit the same `diskcache`
  instance.

The refactor is **out of scope for v1** of this RFC to keep the
diff manageable; tracked as a follow-up.

## Alternatives considered

- **Compute drift inline in writers**: rejected — duplicates
  parsing logic across three writers and the scorer.
- **Keep major-only outdatedness**: rejected — defeats the
  RFC-0008 specification and leaves users without patch-level
  signal, which is the most common upgrade path.
- **Use `packaging.version` for SemVer comparison**: under
  consideration. Maven versions are not strict SemVer (qualifiers,
  Maven version ordering rules), so a project-local comparator
  reusing `MavenVersion` is preferred for the first cut.

## Cost estimate

1.5–2 days:

- New domain DTOs and use case step
- Wire registries into `GenerateFreezeReport` via bootstrap
- Update three writers + console
- Update `_score_outdatedness` to read from version statuses
- Tests for drift classification edge cases (missing patch
  component, alpha/beta/rc qualifiers, version ranges)

## Success metrics

- Every library in the catalog produces a `LibraryVersionStatus`
  (with `latest=None` when both registries return 404).
- A reference catalog with mixed patch/minor/major drift produces
  a risk score top-10 visibly different from the changelog-only
  baseline (patch- and minor-outdated libs surface).
- README's "Version status" claim becomes accurate.
- HTTP request count is bounded by `len(libraries)` per registry,
  with cache hits serving repeated runs.
