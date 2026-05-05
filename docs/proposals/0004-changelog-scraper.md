# RFC-0004: Changelog scraping for major upgrades

**Status:** In progress
**Created:** 2026-05-03
**Related JTBDs:** JTBD-6
**Depends on:** none

## Problem

When a dependency has a major version upgrade available, the cost
of the upgrade is dominated by breaking changes. Today the tool
flags the major bump but offers no information about what changed
or where to read about it.

A team weighing whether to take a major upgrade now or defer it
needs at minimum:

- A link to the changelog or release notes for the target version
- A signal that breaking changes are present (or that the upgrade
  is purely additive)

## Proposed solution

For each dependency with an available major version upgrade, the
tool attempts to discover the changelog and surface a one-line
signal in the report.

Discovery sources, in order of preference:

1. **GitHub Releases** for the artifact's source repo, if the POM
   advertises a `<scm><url>` pointing to GitHub
2. **`CHANGELOG.md` at the repo root** on the default branch
3. **Maven `<url>` pointing to a project page** (best-effort, may
   not yield a changelog directly)

Once content is retrieved, a lightweight heuristic flags whether
breaking changes are likely:

- Headings or bullets containing "BREAKING", "breaking change",
  "removed", "incompatible" → 🔴 likely breaking
- Otherwise → 🟢 no breaking change signal detected

The tool does not attempt full semantic analysis of changelogs.
The output is an indicator, not a guarantee.

Example output:

```
📜 Major upgrades available
   com.squareup.retrofit2:retrofit  2.9.0 → 3.0.0
       🔴 Breaking changes likely
       https://github.com/square/retrofit/releases/tag/3.0.0

   org.jetbrains.kotlinx:kotlinx-coroutines-core  1.7.3 → 2.0.0
       🟢 No breaking signal detected (additive release notes)
       https://github.com/Kotlin/kotlinx.coroutines/releases/tag/2.0.0
```

## Alternatives considered

- **Skip the heuristic, only show the link**: simpler, but less
  useful. Reviewers still have to open every link to know whether a
  bump is risky.
- **Use a paid service (release-please, dependabot insights)**:
  rejected — paid dependency for an open-source tool; data is
  freely scrapable.
- **Parse semver pre-1.0 conventions**: a 0.x → 1.0 bump is by
  convention breaking. This refinement can be layered on top of the
  basic heuristic later.

## Cost estimate

Small to medium. ~2 days:

- POM scraping for SCM URL (already in scope for other features)
- GitHub Releases API integration with caching
- Fallback fetcher for `CHANGELOG.md` on the default branch
- Breaking-change heuristic and unit tests on real-world changelogs

## Success metrics

- ≥70% of dependencies with a major upgrade available yield a
  changelog link
- The breaking-change heuristic agrees with hand-labeled ground
  truth on a 30-sample test set ≥90% of the time
- The feature adds < 1 second to report generation in the common
  case (no major upgrades available)
