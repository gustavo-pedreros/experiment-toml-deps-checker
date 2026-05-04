# RFC-0005: Toolchain compatibility matrix

**Status:** Shipped — TOOL-KC-001 (Kotlin↔Compose), TOOL-KSP-001 (Kotlin↔KSP), TOOL-AGP-001 (AGP↔Gradle) (Step 16)
**Created:** 2026-05-03
**Related JTBDs:** JTBD-4
**Depends on:** none

## Problem

Several Android toolchain components are coupled by official
compatibility matrices that the build tools rarely warn about
proactively:

- **Kotlin ↔ Compose Compiler**: each Kotlin version requires a
  specific Compose Compiler version
- **Kotlin ↔ KSP**: KSP versions are pinned to Kotlin
  (`<kotlin>-<ksp>`)
- **AGP ↔ Gradle**: AGP X requires Gradle ≥ Y
- **AGP ↔ Java / JDK**
- **Hilt ↔ Kotlin / KSP**

A mismatch silently produces flaky builds, Compose-runtime
incompatibilities, or annotation processor failures. Teams discover
these only when a developer's machine fails to build.

The freeze report is the natural place to validate consistency, so
the team enters QA without latent toolchain landmines.

## Proposed solution

Maintain a curated compatibility matrix in the tool's data
directory and validate the project's toolchain against it on every
run.

```
data/
└── compatibility/
    ├── kotlin-compose.yaml
    ├── kotlin-ksp.yaml
    ├── agp-gradle.yaml
    └── agp-java.yaml
```

Example matrix entry:

```yaml
# kotlin-compose.yaml
schema_version: 1
last_updated: 2026-04-30
compatibility:
  - kotlin: "1.9.22"
    compose_compiler: "1.5.8"
  - kotlin: "1.9.20"
    compose_compiler: "1.5.5"
  - kotlin: "2.0.0"
    compose_compiler: "1.5.14"
```

Output section:

```
🧬 Toolchain consistency
   ✅ Kotlin 1.9.22 ↔ Compose Compiler 1.5.8 — OK
   ❌ AGP 8.2.0 requires Gradle ≥ 8.2, detected 8.0 — INCONSISTENT
       Recommended action: upgrade Gradle wrapper to 8.2 or downgrade
       AGP to 8.1.x
   ⚠️  KSP 1.9.20-1.0.14 detected, but Kotlin is 1.9.22
       Recommended action: bump KSP to 1.9.22-1.0.17
```

The matrix is shipped bundled and refreshed via the same hybrid
mechanism as the deprecation knowledge base (see
[ADR-0003](../adr/0003-bundled-plus-remote-deprecation-kb.md)).

## Alternatives considered

- **Live API to JetBrains / Google**: no public, structured API
  exists for these matrices. Scraping is unreliable.
- **Letting Gradle warn at build time**: insufficient. Gradle's
  warnings are buried in build output and inconsistent across
  these tools.
- **Skipping this and pointing at official docs**: rejected — this
  is one of the most differentiating features of the tool for
  Android-focused teams.

## Cost estimate

Medium to large for the initial seeding of the matrices and the
validator. ~3-4 days:

- YAML schema and validator for each matrix
- Project metadata extraction (Kotlin / AGP / Compose / KSP / Hilt
  versions from `libs.versions.toml` and Gradle wrapper)
- Report rendering with actionable recommendations
- Initial seed for the four primary matrices

Ongoing maintenance: small (~30 minutes per Kotlin or AGP
release). Community PRs are expected to take over much of this
once seeded.

## Success metrics

- Detected inconsistencies on a hand-labeled set of 10 known-bad
  configurations: 100%
- False positive rate on 10 known-good configurations: 0%
- Time to update the matrix after a new Kotlin or AGP release:
  ≤ 1 week
