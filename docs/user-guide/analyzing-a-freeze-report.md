# Analyzing a freeze report

This chapter covers the `/analyze-freeze` Claude Code skill — the
canonical consumer of the CSV outputs produced by
`gradle-deps-monitor check`. It assumes you have already run a
freeze ([Getting started](getting-started.md)) and have a directory
like `freeze-reports/2026-05-19/` containing `freeze-inventory.csv`
and `freeze-findings.csv`.

> If you are not using Claude Code, the runner under
> `tools/analytics/runner.py` is invocable directly. The skill is a
> thin wrapper that adds a procedure for Claude to follow.

## Background: what counts as a "skill"

`/analyze-freeze` is the project's first **Claude Code skill** —
distinct from the **sub-agents** in `.claude/agents/` (`housekeeper`,
`test-runner`). The two mechanisms are sometimes conflated; the
distinction matters because it changes how you invoke them and what
context they see.

| Dimension | Sub-agent (`.claude/agents/<name>.md`) | Skill (`.claude/skills/<name>/SKILL.md`) |
|---|---|---|
| **What it is** | A specialised worker Claude dispatches into a separate conversation | A capability / recipe Claude loads into its own context |
| **Invocation** | The main thread decides to dispatch via the `Agent` tool; you can also request it by name ("run the housekeeper") | You type `/<skill-name>`, or Claude auto-loads when your request matches the skill's description |
| **Tools** | Own allowlist in frontmatter (`tools: Bash, Read, …`) | Inherits whatever tools the current thread already has |
| **Context** | Fresh conversation every run; returns one summary string | Inherits the current conversation; can iterate with you |
| **Model** | Can pin its own (`model: haiku`) | Uses the main thread's model |
| **Best for** | Bounded, repeatable, low-reasoning chores worth running on a cheaper model | Parameterised recipes where the value is the procedure + canonical inputs |

`/analyze-freeze` is genuinely a skill: the value is the canonical
queries and the runner contract, not isolation from the main thread.
When you type `/analyze-freeze freeze-reports/2026-05-19/`, Claude
(main thread) loads `SKILL.md`, runs the documented procedure, reads
stdout, and continues the conversation with you — no child process,
no fresh context.

## Installing the analytics extra

The skill depends on the `[analytics]` optional extra, which pulls
DuckDB and tabulate:

```bash
pip install -e ".[analytics]"
```

Two packages total — no pandas, no numpy. See
[ADR-0010](../adr/0010-analytics-stack-duckdb.md) for why the stack
looks like this and what would trigger reconsideration (the
RFC-0010 HTML export is the natural next user).

## Running the skill

From Claude Code:

```
/analyze-freeze freeze-reports/2026-05-19/
```

The procedure Claude follows is documented in
[`.claude/skills/analyze-freeze/SKILL.md`](../../.claude/skills/analyze-freeze/SKILL.md);
in short: it resolves the path, verifies the two CSVs exist, runs
`python tools/analytics/runner.py --dir <abs-path>`, reads stdout,
summarises the top observations for you, and offers next actions.

From the command line directly:

```bash
python tools/analytics/runner.py --dir freeze-reports/2026-05-19/
```

Both paths produce the same Markdown to stdout.

## What you get back

A single Markdown document with one `## <Title>` section per
canonical query, in numeric order. The queries are designed so that
each section answers a question a reviewer asks every freeze; their
union covers every dimension of the RFC-0017 CSV contract.

### Worked example — Sunflower

The Android team's [Sunflower sample](https://github.com/android/sunflower)
makes a useful 50-library example. After running:

```bash
gradle-deps-monitor check external-project/sunflower/gradle \
    --out reports/sunflower-2026-05-19 \
    --module-usage --risk-score
python tools/analytics/runner.py --dir reports/sunflower-2026-05-19/
```

You get (abbreviated):

```markdown
## Top risk
| alias                       | coordinate                       | version    | risk_score | risk_level | drift | cves | license_tier  |
| androidx-compose-bom        | androidx.compose:compose-bom     | 2024.05.00 |         28 | low        | major |    0 | permissive    |
| androidx-compose-foundation | androidx.compose.foundation:…    | 1.6.7      |         28 | low        | minor |    0 | permissive    |
… (top 15 by risk_score) …

## Drift × severity
| drift | risk_level | libraries |
| major | low        |         4 |
| minor | low        |        40 |
| none  | none       |         2 |
| none  | low        |         4 |

## Compound: duplicates with CVEs
> No rows for this query against this report.

## Pre-release tiers in the catalog
| alias                          | coordinate                 | version        | stability_tier | drift | latest_stable |
| material                       | …android.material:material | 1.13.0-alpha01 | alpha          | minor | 1.14.0        |
| glide                          | …glide:compose             | 1.0.0-beta01   | beta           | none  | 1.0.0-beta09  |
| androidx-paging-compose        | …paging:paging-compose     | 3.3.0-rc01     | rc             | minor | 3.5.0         |
| accompanist-systemuicontroller | …accompanist:…             | 0.34.0         | pre_1_0        | minor | 0.36.0        |
| guava                          | com.google.guava:guava     | 33.1.0-jre     | unknown        | none  | 23.0          |

## Inactive / unhealthy libraries
| alias | coordinate  | version | health_status | modules_using |
| junit | junit:junit | 4.13.2  | inactive      |             0 |

## License risk cohort
| alias | coordinate             | version    | license_tier  |
| junit | junit:junit            | 4.13.2     | weak_copyleft |
| guava | com.google.guava:guava | 33.1.0-jre | unknown       |

## Findings by section × severity
| section        | common_severity | findings |
| Compliance     | error           |        1 |
| Toolchain      | error           |        1 |
| Library Health | error           |        1 |
| License        | warning         |        2 |
| Catalog Health | warning         |        1 |
| Catalog Health | info            |        2 |
| Catalog Health | suggestion      |        2 |

## BoM coverage
| bom_parent           | libraries_in_cohort |
| (unmanaged)          |                  41 |
| androidx-compose-bom |                   9 |
```

The story this tells:

- **Top risk + Drift × severity**: 44 of 50 libraries have non-zero
  drift, but none are above `LOW` risk. The compose BoM family
  (10 libraries at `risk_score 28`) dominates the top — they all
  move together; bumping the BoM addresses them in one stroke.
- **Compound: duplicates with CVEs**: the empty result is the
  expected outcome on a clean catalog. The query exists to catch
  regressions where a stale duplicate alias quietly accumulates a
  CVE-bearing version.
- **Pre-release tiers**: five libraries are pinned to a non-stable
  tier. `material 1.13.0-alpha01` is the most concerning (alpha is
  the weakest tier); `accompanist-systemuicontroller 0.34.0` is at
  `pre_1_0` — accepted convention for libraries that never reach
  `1.0`. `guava` showing up here as `unknown` is the version-string
  parser hedging on `33.1.0-jre`.
- **Inactive**: `junit:junit 4.13.2` is the canonical example —
  inactive upstream, but with `modules_using = 0` it's not a
  blocker, just maintenance debt.
- **License risk**: only `junit` (weak copyleft) and `guava`
  (unknown). Both expected.
- **Findings × severity**: 10 findings total. The three `error`s
  (Compliance, Toolchain, Library Health) are the action items.
- **BoM coverage**: 9 of 50 libraries are managed by the Compose
  BoM. The 41 unmanaged libraries are mostly first-party
  AndroidX modules — expected.

## The "scanner not run" hint

If you ran `gradle-deps-monitor check` without `--risk-score`, the
`Top risk` and `Drift × severity` sections will render as:

```markdown
## Top risk

> Scanner not run for this dimension. Re-run
> `gradle-deps-monitor check --risk-score` to populate this section.
```

The same shape applies to `Compound: duplicates with CVEs` when
`GITHUB_TOKEN` is unset (no CVE scanner) — the section names the
missing credential rather than guessing.

## Adding a new canonical query

The canonical query library is meant to grow. See
[`tools/analytics/queries/INDEX.md`](../../tools/analytics/queries/INDEX.md)
for the criteria a query must meet to be canonical (generalizable,
repeatable, compresses signal, self-contained SQL) and the step-by-
step procedure for adding one. In summary:

1. Validate against the four canonical criteria.
2. Add `NN_<name>.sql` to `tools/analytics/queries/`.
3. Add a row to `INDEX.md` and a title to `TITLES` in `render.py`.
4. Update `schema.sql` only if you introduce a new column reference.
5. Smoke-test: `python tools/analytics/runner.py --dir
   reports/sunflower-2026-05-19/` should show your new section.

Non-canonical (project-specific or one-off) queries belong in
ad-hoc scripts, not in `queries/`.

## When NOT to use this skill

- For per-commit diffs against a previous freeze — use
  `gradle-deps-monitor diff old.json new.json` instead. The skill
  is built for a *single* freeze; diff analytics is a separate
  concern (and a future RFC).
- For an HTML report — currently 📋 Planned in Phase 8 as
  [RFC-0010](../proposals/0010-html-export.md). The same canonical
  `.sql` files will power that consumer when it ships.
- For arbitrary "what's in this CSV?" queries — those are
  legitimate but don't belong in the canonical library; run
  DuckDB or any CSV viewer directly.
