# RFC-0014: Maven BoM (Bill of Materials) support

**Status:** Proposed
**Created:** 2026-05-06
**Related JTBDs:** JTBD-1 (know what is outdated), JTBD-3 (catalog
hygiene), JTBD-6 (rank by risk)
**Depends on:** [RFC-0013](0013-version-status-first-class.md)
(version status infrastructure)

## Problem

Modern Android catalogs declare BoMs (Bill of Materials platforms)
for entire dependency families:

- **Firebase BoM** → `firebase-analytics`, `firebase-auth`,
  `firebase-crashlytics`, `firebase-messaging`, …
- **Compose BoM** (`androidx.compose:compose-bom`) → all
  `androidx.compose.*` artefacts
- **OkHttp BoM** → `okhttp`, `okhttp-logging-interceptor`,
  `mockwebserver`, …

Children declared with `version.ref` omitted (or with no version
at all) inherit their version from the BoM. Today the tool:

1. **Treats parent and children as independent.** The BoM appears
   as one library; children appear as separate libraries with
   missing or stale versions.
2. **Produces incorrect or empty data for children.** Libraries
   declared without a version field produce `Library.version`
   strings like `""` that confuse stability classification, drift
   computation, and CVE matching.
3. **Misses the "bumping the BoM updates these N libs" signal.**
   Reviewers see N independent stale libraries instead of one
   actionable BoM upgrade.
4. **Does not propagate stability or drift from parent to
   children.** A pinned `firebase-bom = 33.0.0` with `latest =
   34.0.0` should ripple a "major-behind" signal across every
   irrigated child.

## Proposed solution

Three pieces: detection, resolution, and propagation.

### 1. BoM detection

A library entry is treated as a BoM when **any** of the following
hold:

- `artifactId` ends in `-bom` (e.g. `firebase-bom`,
  `compose-bom`).
- `artifactId` ends in `-platform`.
- The entry is referenced in any `build.gradle(.kts)` via
  `platform(libs.x)` or `enforcedPlatform(libs.x)`. (Reuses the
  module-usage scanner from [RFC-0007](0007-module-usage-map.md);
  optional refinement.)

Detection produces a `BomLibrary` marker on the catalog entry; it
is reported separately from regular libraries.

### 2. BoM resolution

New infrastructure adapter `BomResolver` (under
`infrastructure/resolvers/bom_resolver.py`):

- Fetches the BoM POM from Maven Central / Google Maven (reuses
  the cached registry from [RFC-0013](0013-version-status-first-class.md)).
- Parses `<dependencyManagement><dependencies>`.
- Returns:

```python
@dataclass(frozen=True)
class ManagedCoordinate:
    group: str
    artifact: str
    version: MavenVersion

@dataclass(frozen=True)
class BomResolution:
    bom_alias: str
    bom_coordinate: str
    bom_version: MavenVersion
    managed: tuple[ManagedCoordinate, ...]
```

### 3. Propagation to other features

- **`Library` gains `version_source`**:
  ```python
  class VersionSource(StrEnum):
      LITERAL     = "literal"      # version set inline
      VERSION_REF = "version-ref"  # via [versions]
      FROM_BOM    = "from-bom"     # version comes from a BoM
  ```
  Children resolved via a BoM carry `version_source = FROM_BOM`
  and a `bom_alias` reference.
- **Risk score (`_score_outdatedness`)**: a child with
  `FROM_BOM` source is scored using the BoM's drift, not its
  own (which would be `unknown` because the catalog declares no
  version for it). The breakdown row reads "via firebase-bom
  (major-behind)".
- **CVE / library health checks**: still run per-child, since
  the BoM does not patch CVEs in children itself; only the
  effective version is needed to query advisories accurately.
- **Writers**: each managed library carries a badge
  `via firebase-bom 33.1.0` next to its row; a new BoM section
  groups managed libraries under their parent.

### 4. Catalog Health rule

New rule **HDX-009 — `library declared without version and no BoM
resolves it`**. Severity: `error`. Catches the regression where a
child entry survives a BoM removal.

### 5. Schema bump

`freeze.json.schema_version`: `1.0.0` → `1.1.0` (additive — new
optional fields per
[ADR-0008](../adr/0008-json-schema-semver.md)).

New JSON shape excerpts:

```json
{
  "schema_version": "1.1.0",
  "libraries": [
    {
      "alias": "firebase-analytics",
      "coordinate": "com.google.firebase:firebase-analytics",
      "version": "21.5.0",
      "version_source": { "kind": "from-bom", "bom_alias": "firebase-bom" }
    }
  ],
  "boms": [
    {
      "alias": "firebase-bom",
      "coordinate": "com.google.firebase:firebase-bom",
      "version": "33.0.0",
      "managed_count": 24
    }
  ]
}
```

## Alternatives considered

- **Hand-curated list of known BoMs**: rejected. Doesn't scale to
  internal/private BoMs; needs constant maintenance.
- **Resolve BoMs only when explicitly flagged via CLI**: rejected.
  Defeats the freeze-time accuracy goal; teams using BoMs already
  expect them to "just work".
- **Treat children as if they had the BoM's version inline**:
  rejected. Loses the parent-child relationship in reports, which
  is the most actionable signal.
- **Resolve at parse time vs at use-case time**: chosen
  use-case time (alongside version status), keeping parsing pure.

## Cost estimate

2–3 days:

- Detection heuristic + tests
- `BomResolver` adapter (POM fetch + parse)
- Domain integration (`VersionSource`, `bom_alias` on `Library`)
- Use-case wiring after RFC-0013 lands
- Markdown / JSON / Slack writer updates
- Catalog health rule HDX-009
- Fixtures: real Firebase BoM, real Compose BoM, real OkHttp BoM
- Tests for missing BoM, BoM with empty management, BoM upgrade
  major-behind scenario

## Success metrics

- Running against a real Mach catalog using Firebase BoM produces:
  - The BoM is detected and resolved.
  - All `firebase-*` children show `via firebase-bom <version>`.
  - Risk score outdatedness for children mirrors the BoM, not
    `unknown`.
- Removing the BoM line from the catalog (without removing
  children) triggers HDX-009 errors for every orphaned child.
- A real Compose catalog produces consistent "via compose-bom"
  badges for all `androidx.compose.*` libraries.
