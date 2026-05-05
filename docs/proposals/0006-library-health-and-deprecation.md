# RFC-0006: Library health and deprecation prediction

**Status:** Shipped — curated KB (26 entries) + Maven POM relocation + inactivity heuristic (Step 17)
**Created:** 2026-05-03
**Related JTBDs:** JTBD-3
**Depends on:** [ADR-0003](../adr/0003-bundled-plus-remote-deprecation-kb.md)

## Problem

"Outdated" is not the only signal that a dependency needs
attention. A library may be:

- Officially deprecated (ButterKnife, dagger-android, the support
  library)
- In maintenance-only mode (RxJava 2.x, KAPT)
- Abandoned (no release in 24+ months)
- Replaced by an industry-standard successor

The current tool reports none of these signals. Teams may keep
dependencies that are technically up-to-date but that should be
migrated.

## Proposed solution

Combine three signals into a "Library Health" section of the
report.

### Signal 1 — Curated deprecation knowledge base

A YAML file shipped with the tool, listing well-known deprecation
paths with replacements and migration guides.

```yaml
- id: butterknife
  from: "com.jakewharton:butterknife"
  replacement: "androidx.viewbinding (built-in)"
  reason: "Author deprecated in 2020; ViewBinding is the official replacement."
  severity: high
  migration_url: "https://github.com/JakeWharton/butterknife#dropping-butterknife"
  verified_at: 2026-04-15
```

Distribution follows the bundled-plus-remote model
([ADR-0003](../adr/0003-bundled-plus-remote-deprecation-kb.md)).

### Signal 2 — POM `<relocation>` tags (automatic)

The POM file for an artifact may declare it has been relocated:

```xml
<distributionManagement>
  <relocation>
    <groupId>new.group.id</groupId>
    <artifactId>new-artifact</artifactId>
    <message>Moved to new.group.id:new-artifact</message>
  </relocation>
</distributionManagement>
```

When detected, this is reported as a high-confidence deprecation
without curation. This is the official Maven mechanism and is 100%
reliable when present.

### Signal 3 — Inactivity (heuristic)

When no curated entry and no relocation tag exist, an inactivity
heuristic kicks in:

- Last release > 24 months ago → `⚠️  inactive`
- Last release > 36 months ago → `⚠️  likely abandoned`

Inactivity alone is a soft signal, presented as an informational
warning rather than a recommendation.

### Combined output

```
📉 Library health
   ❌ com.jakewharton:butterknife 10.2.3 — Deprecated by author
       Replacement: androidx.viewbinding (built-in)
       Source: curated KB

   ❌ com.android.support:appcompat-v7 28.0.0 — Relocated by maintainer
       Replacement: androidx.appcompat:appcompat
       Source: POM relocation tag (automatic)

   ⚠️  io.reactivex.rxjava2:rxjava 2.2.21 — Inactive
       Last release: 2021-04-13 (1118 days)
       Suggested successor: kotlinx-coroutines / Flow
       Source: inactivity heuristic + curated KB
```

## Alternatives considered

- **Curated KB only**: simpler but high maintenance, and misses
  every deprecation not yet curated. The hybrid approach reduces
  the curation burden by ~50% in practice.
- **Inactivity heuristic only**: too noisy, false positives on
  stable, finished libraries (e.g., Apache Commons modules).
- **Crowdsourced data via OSV or libraries.io**: useful as future
  signals but not as a replacement for curated paths with
  recommended successors.

## Cost estimate

Medium. ~3-4 days for the initial implementation:

- YAML schema and loader for the curated KB
- POM relocation tag detection (extends existing POM-fetching code)
- Inactivity heuristic from Maven metadata `<lastUpdated>`
- Initial seed of 20-30 curated entries covering the highest-impact
  Android deprecations (support library, ButterKnife, RxJava2,
  KAPT, dagger-android, Volley, Crashlytics SDK, etc.)
- Report rendering

## Success metrics

- All 20+ entries in the seed knowledge base resolve correctly on
  a fixture project
- POM relocation detection works on a corpus of known-relocated
  artifacts (e.g., `com.android.support` → `androidx`)
- Community contributes ≥5 new entries within 6 months of release
  (signal that the format is approachable)
