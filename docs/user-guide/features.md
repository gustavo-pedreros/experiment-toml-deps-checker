# Feature deep-dives

The [Getting Started](getting-started.md) page lists what the tool
checks at a glance. This page goes deeper on the five features that
benefit most from explanation: CVE scanning, BoM resolution, License
audit, Module Usage map, and Risk Score.

## CVE scanning

The Security section runs zero, one, or both of these scanners
depending on which credentials are present:

| Scanner | Source | Credentials | Default TTL |
|---|---|---|---|
| GHSA | GitHub Advisory Database (GraphQL) | `GITHUB_TOKEN` (zero scopes) | 24 h |
| OSS Index | Sonatype OSS Index (REST) | `OSSINDEX_USER` + `OSSINDEX_API_KEY` | 24 h |

When both are present a composite scanner runs them in parallel and
deduplicates by `(coordinate, CVE-ID)`. When neither is present the
Security section renders an explicit `⊘ scan not configured` rather
than disappearing — so you can tell "scanner ran clean" apart from
"scanner didn't run".

### Severity vocabulary

Each scanner reports `CRITICAL` / `HIGH` / `MEDIUM` / `LOW` /
`UNKNOWN`. These map into the cross-section `CommonSeverity` enum
the rest of the tool speaks:

| Advisory severity | CommonSeverity | Icon |
|---|---|---|
| `CRITICAL`, `HIGH` | `ERROR` | 🔴 |
| `MEDIUM` | `WARNING` | 🟡 |
| `LOW`, `UNKNOWN` | `INFO` | 🔵 |

`--fail-on-errors` (RFC-0018) fails the build on **`CRITICAL`
only** — `HIGH` is opt-in via `--warn-on high-vulnerability` so
the gatekeeper stays useful on catalogs with a steady backlog of
HIGH findings.

### Refreshing CVE data

The 24-h TTL means a CVE published today is invisible until your
cache expires. Two ways to force a fresh scan:

```bash
gradle-deps-monitor check /path/to/gradle --no-cache
gradle-deps-monitor check /path/to/gradle --cache-ttl 0
```

Both are equivalent for one-off freshness checks. Routine CI runs
usually keep the default TTL — the noise cost of every-run refreshes
isn't worth the marginal freshness for routine reporting.

## BoM resolution

When the catalog declares any artifact whose alias ends in `-bom` or
`-platform`, the BoM resolver:

1. Fetches the BoM's `<dependencyManagement>` block from Maven.
2. Lists every managed coordinate in the report's **BoMs** section.
3. Cross-references catalog libraries that match those coordinates
   and marks them as "managed by" the BoM.
4. Replaces the `version` displayed for managed children with the
   BoM-resolved version, so the catalog and the actual build stay
   consistent.

The Markdown report shows the managed-children list per BoM:

```
### `compose_bom` — `androidx.compose:compose-bom` `2024.06.00`
- Manages **128** coordinates.
- Children in catalog: `compose-ui`, `compose-foundation`,
  `compose-material3`, `compose-runtime`.
```

`inventory.csv` carries the `bom_parent` column so you can filter
the catalog by BoM in Excel or Sheets.

## License audit

Every catalog library's POM is fetched and its `<licenses>` block
classified into one of four tiers:

| Tier | Examples | What it means |
|---|---|---|
| `PERMISSIVE` ✅ | Apache-2.0, MIT, BSD-3-Clause | No distribution conditions worth flagging. |
| `WEAK_COPYLEFT` ⚠ | LGPL-2.1, MPL-2.0, EPL-2.0 | Distribution conditions apply to the library, not your app — usually fine but worth knowing about. |
| `STRONG_COPYLEFT` 🔴 | GPL-3.0, AGPL-3.0 | Distribution conditions can apply to your app. Usually a hard block for closed-source Android distribution. |
| `UNKNOWN` ❓ | POM has no `<licenses>` element | Worth investigating manually. |

`--fail-on-errors` blocks on `STRONG_COPYLEFT` only. Use
`--warn-on license` to surface `WEAK_COPYLEFT` and `UNKNOWN`
without blocking.

The classifier respects GPL's classpath exception
([RFC-0023](../proposals/0023-license-classpath-exception.md)) —
JDK-style classpath-exception GPL is recognised as PERMISSIVE.

## Module Usage map (opt-in: `--module-usage` / `-m`)

When enabled, the tool statically scans every `build.gradle` and
`build.gradle.kts` file in the project and counts how each catalog
alias is referenced:

```bash
gradle-deps-monitor check /path/to/gradle --module-usage
```

Three counts per library:

| Count | What it measures |
|---|---|
| `impl` | Modules that pull the library in via `implementation`, `runtimeOnly`, etc. |
| `api` | Modules that re-export it via `api` (transitively visible to consumers) |
| `test only` | Modules that only use it under `testImplementation`, `androidTestImplementation`, etc. |

The scanner recognises every Gradle catalog accessor form: dotted
(`libs.foo.bar`), camelCase (`libs.fooBar`), bundle expansion
(`libs.bundles.<name>`), BoM wrappers (`platform(libs.x.bom)`,
`enforcedPlatform(...)`), and underscore variants
([RFC-0022](../proposals/0022-module-scanner-accessor-coverage.md)).

The Module Usage Map answers operational questions you can't get
from the catalog alone:

- "Which libraries are declared but never referenced?"
  → look for libraries absent from the table.
- "Which library is most depended-on?"
  → top of the per-library table.
- "Which module has the largest direct-dep surface?"
  → the per-module top-N table.

## Risk Score (opt-in: `--risk-score` / `-r`, experimental)

Computes a composite 0-100 score per library across six weighted
dimensions:

| Dimension | Default weight | What feeds it |
|---|---|---|
| `outdatedness` | 25 | Major-version drift contributes the most; patch the least. |
| `cve` | 30 | One CRITICAL CVE pegs this dimension; HIGH less so. |
| `abandonment` | 15 | Library Health signals: `INACTIVE`, `DEPRECATED`, `RELOCATED`. |
| `blast_radius` | 15 | How many modules consume the library (requires `--module-usage`). |
| `compliance` | 10 | Play Store compliance hits on this library. |
| `license` | 5 | Tier penalty: `STRONG_COPYLEFT` >> `WEAK_COPYLEFT` > `UNKNOWN`. |

The numeric output is bucketed into LOW / MEDIUM / HIGH / CRITICAL
via three configurable thresholds (defaults: 30 / 50 / 70).
Re-weight everything in `[risk]` (see
[Configuration](configuration.md)).

The score is most informative as a **trend across freezes**, not as
an absolute. A library at score 45 today is more interesting if it
was 25 last week than if it has been at 45 for a month. The diff
report surfaces score deltas explicitly.

### Why a score, not a single threshold

A score collapses six dimensions into one number you can sort by
and compare across libraries. The Risk Score table in the Markdown
report shows each dimension's contribution with an ASCII bar:

```
| Dimension     | Bar              | Score   | Detail                          |
|---------------|------------------|---------|---------------------------------|
| outdatedness  | █████████████░░  | 22 / 25 | major drift: 2.x → 5.x          |
| cve           | ███████████████  | 30 / 30 | 1 CRITICAL, 2 HIGH              |
| abandonment   | ███░░░░░░░░░░░░  |  5 / 15 | inactive 18 mo                   |
| blast_radius  | ████████░░░░░░░  | 12 / 15 | 47 modules consume directly      |
| compliance    | ░░░░░░░░░░░░░░░  |  0 / 10 | —                                |
| license       | ░░░░░░░░░░░░░░░  |  0 /  5 | Apache-2.0                       |
```

so you can see which dimension drives the score rather than only
the aggregate.
