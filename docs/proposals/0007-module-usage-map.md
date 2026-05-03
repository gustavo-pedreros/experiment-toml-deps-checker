# RFC-0007: Module usage map

**Status:** Proposed
**Created:** 2026-05-03
**Related JTBDs:** JTBD-6
**Depends on:** none

## Problem

In a multi-module project (the primary user has roughly 200
modules sharing a single version catalog), the cost of a
dependency upgrade is dominated by its blast radius: how many
modules use it, whether it leaks through public APIs, and whether
the affected modules are in the critical path.

Today the report has no awareness of which modules consume which
dependency. The team must answer "who uses okhttp?" by hand.

## Proposed solution

Optionally enable a "Module usage map" pass that reads each
module's `build.gradle(.kts)` and produces a usage table per
dependency.

This is opt-in via a flag, because it materially increases run
time on large projects (file walks, regex parses). Users running
the tool in CI for a quick freeze check can leave it off; users
investigating a specific upgrade locally can turn it on.

```
toml-deps-checker /path/to/project --module-usage
```

Or, in `config.toml`:

```toml
[features]
module_usage_map = true
```

Output section:

```
🗺️ Module usage for okhttp 4.9.1 → 4.12.0
   Direct dependents:    47 modules
   Transitive dependents: 138 modules
   Exposed via `api`:     12 modules (may break consumers)
   Test-only:              8 modules

   Examples (direct):
     :feature:auth, :feature:payments, :network:core, ...
```

The map is also useful at a per-module summary level:

```
🗺️ Module-level summary (top 5 by direct dependency count)
   :network:core      ─ 34 direct deps
   :feature:payments  ─ 28 direct deps
   :common:utilities  ─ 22 direct deps
   ...
```

### Implementation sketch

The first implementation parses `build.gradle(.kts)` files
directly (regex / lightweight tokenization) to extract:

- `implementation libs.foo.bar` and similar configurations
- `api libs.foo.bar` (matters for ABI exposure)
- `testImplementation`, `androidTestImplementation` (separated)

A future iteration could shell out to `./gradlew :module:dependencies`
for higher fidelity. That is not in scope for the first cut, since
running Gradle is slow and adds setup complexity.

## Alternatives considered

- **Always on, no flag**: rejected — too costly for the simple
  freeze workflow, and not every team needs this signal.
- **Pure Gradle integration via `./gradlew`**: more accurate but
  slower and requires the project to be in a build-ready state.
  Could be a future opt-in mode (`--module-usage=gradle`).
- **Static analysis with the Kotlin compiler**: overkill for this
  level of fidelity.

## Cost estimate

Medium. ~3 days:

- Walk modules from `settings.gradle(.kts)`
- Parse each module's `build.gradle(.kts)` for dependency
  declarations
- Cross-reference against the version catalog
- Aggregate counts and render

## Success metrics

- On a 200-module project, the pass completes in under 30 seconds
  (without Gradle invocation)
- Direct dependent counts agree with `./gradlew dependencyInsight`
  on a sample set within ±5%
- The flag default is OFF; enabling it does not destabilize the
  default report
