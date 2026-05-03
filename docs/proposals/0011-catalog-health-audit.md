# RFC-0011: Catalog health audit

**Status:** Proposed
**Created:** 2026-05-03
**Related JTBDs:** JTBD-3
**Depends on:** none

## Problem

Beyond the dependencies it lists, a `libs.versions.toml` file is
itself a piece of the project's architecture. Catalogs that miss
the `[plugins]` section, declare versions inline, omit `[bundles]`,
or use inconsistent naming conventions are harder to maintain — and
the consequences scale with the number of modules.

Teams rarely audit the catalog file itself. The freeze report is a
natural moment to do so, both because the file is already being
parsed and because a freeze is a low-stakes window for cleanup
recommendations.

## Proposed solution

Add a "Catalog Health" section to the report that audits the TOML
file against a set of best-practice rules. Each finding includes a
short rationale so the user understands why the recommendation
matters.

### Initial rule set

| Rule ID                              | Severity | What it detects                                                          |
|--------------------------------------|----------|--------------------------------------------------------------------------|
| `catalog.missing-plugins`            | warning  | No `[plugins]` section despite Gradle plugins applied in build files     |
| `catalog.inline-versions`            | info     | Library entries with `version = "x.y.z"` instead of `version.ref`        |
| `catalog.missing-bundles`            | info     | No `[bundles]` section in a multi-module project                         |
| `catalog.duplicate-version-values`   | suggestion | Multiple version keys with identical values (consolidation candidates) |
| `catalog.inconsistent-naming`        | warning  | Mix of camelCase and kebab-case keys                                     |
| `catalog.orphan-version-ref`         | warning  | Version declared but never referenced                                    |
| `catalog.unresolved-version-ref`     | error    | A `version.ref` points to an undeclared version key                      |
| `catalog.duplicate-library`          | error    | The same library declared more than once                                 |
| `catalog.plugins-outside-catalog`    | warning  | Plugins applied with literal versions outside the catalog (build files)  |

The first 8 rules operate on the TOML file alone (cheap). The
ninth requires reading `build.gradle(.kts)` files and is gated
behind the same `--module-usage` flag as
[RFC-0007](0007-module-usage-map.md).

### Pluggable rule architecture

Each rule is a self-contained Python file with a defined
interface:

```python
# checks/catalog_health/missing_plugins_section.py

ID = "catalog.missing-plugins"
SEVERITY = "warning"

def check(catalog: VersionCatalog, project: ProjectMeta) -> Finding | None:
    if catalog.has_section("plugins"):
        return None
    return Finding(
        id=ID,
        severity=SEVERITY,
        message="Missing [plugins] section",
        explanation=(
            "Detected Gradle plugins applied via build.gradle(.kts) "
            "outside the version catalog."
        ),
        benefit=(
            "Centralizing plugin versions in libs.versions.toml "
            "guarantees consistent application across modules and "
            "enables atomic upgrades."
        ),
    )
```

This makes rules independently testable and contributable. New
rules add a single file without touching the core.

### Rule disable list

Some teams may not want certain nudges:

```toml
[catalog_health]
enabled = true

[catalog_health.disabled_rules]
ids = ["catalog.missing-bundles"]
```

### Example output

```
📋 Catalog Health
   ⚠️  Missing [plugins] section
       Detected 4 Gradle plugins applied via build.gradle(.kts)
       outside the version catalog. Consider declaring them here.
       Benefit: centralizing plugin versions guarantees consistent
       application across all 200 modules and enables atomic
       upgrades.

   ℹ️  Inline versions detected (12 entries)
       Examples: kotlinx-serialization, jackson-core, mockk
       Benefit: using version.ref allows related libraries to share
       a single version (e.g., all kotlinx-coroutines artifacts at
       once), preventing drift between sibling libraries.

   💡 8 dependencies share the version "1.9.22"
       (kotlin-stdlib, kotlin-reflect, kotlinx-coroutines-*, ...)
       Consider consolidating under a single `kotlin = "1.9.22"`
       version.ref.

   ✅ Consistent kebab-case naming
   ✅ No duplicate library declarations
   ✅ All version refs resolve correctly
```

## Alternatives considered

- **Lint as a separate command instead of a section in the
  report**: rejected — the freeze report is already being
  generated, the catalog is already being parsed, and the user is
  already paying attention. Bundling avoids a second invocation.
- **Hard-coded rules in the core parser**: rejected — the
  pluggable architecture is more contributor-friendly and allows
  selective disabling.

## Cost estimate

Medium. ~3 days, but most of the cost is up-front design of the
pluggable architecture; subsequent rules cost ~30 minutes each.

- Plugin-style rule loader
- Initial seed of 8 rules listed above
- Configuration support for disabling rules
- Report rendering

## Success metrics

- Each seed rule covered by at least one positive and one negative
  unit test
- Rules can be added without modifying the core
- The rule set remains useful with up to 10% of rules disabled by
  the user (no catastrophic interactions)
