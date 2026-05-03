# RFC-0008: Risk score

**Status:** Proposed
**Created:** 2026-05-03
**Related JTBDs:** JTBD-6
**Depends on:** RFC-0001 (CVE), RFC-0002 (compliance), RFC-0006
(deprecation), RFC-0007 (module usage), RFC-0009 (license)

## Problem

A freeze report can list dozens of dependencies that need
attention. Without a way to rank them, reviewers default to the
loudest signal of the moment (latest CVE, most-discussed library)
rather than the most material risk.

A composite score per dependency, derived from multiple
dimensions, helps focus attention. The challenge is to make it
transparent (no opaque ranking) and tunable (different industries
weigh dimensions differently).

## Proposed solution

Compute a 0–100 risk score per dependency, summing six independent
contributions. The score is **opt-in** (see [ADR-0004](../adr/0004-risk-score-opt-in-with-disclaimer.md)).

### Components

| Dimension     | Cap | Source                                                              |
|---------------|-----|---------------------------------------------------------------------|
| Outdatedness  | 25  | Major / minor / patch gap vs latest stable                          |
| CVE severity  | 30  | RFC-0001                                                            |
| Abandonment   | 15  | RFC-0006 (last release age, deprecation status)                     |
| Blast radius  | 15  | RFC-0007 (number of modules using it)                               |
| Compliance    | 10  | RFC-0002 (Play Store deadlines applicable to this dep)              |
| License       | 5   | RFC-0009 (restrictive licenses for commercial use)                  |

Each dimension's contribution is computed by a transparent function
defined in code and documented in the report. Examples:

```
Outdatedness:
  patch_diff      → 0-5
  minor_diff      → 5-15
  major_diff (1)  → 15-20
  major_diff (≥2) → 25

CVE severity:
  no CVE          → 0
  LOW             → 5  per finding (capped at 10)
  MEDIUM          → 10 per finding (capped at 20)
  HIGH            → 20 per finding (capped at 25)
  CRITICAL        → 30
```

### Configuration

Weights and thresholds are configurable per project:

```toml
[risk_weights]
outdatedness = 25
cve          = 30
abandonment  = 15
blast_radius = 15
compliance   = 10
license      = 5

[risk_thresholds]
critical = 70
high     = 50
medium   = 30
```

A fintech project might increase `cve` and `license`. A small
indie app might lower `compliance`. Defaults are calibrated for
general-purpose Android applications.

### Output

```
⚖️ Risk Score (experimental)

This indicator is under active refinement. Scores are most
meaningful when compared across multiple freeze reports — a single
number in isolation is less informative than the trend over time.

Top 5 risk-weighted dependencies:

#1  com.squareup.okhttp3:okhttp        4.9.1 → 4.12.0       Score 78
    Outdated (minor)        ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓                12 / 25
    CVE-2023-3635 (HIGH)    ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓             20 / 30
    Last release 8 mo ago   ▓▓▓▓▓                              5 / 15
    Used in 47 modules      ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓                  14 / 15
    Compliance: clean       ▓                                  0 / 10
    License: Apache 2.0     ▓                                  0 / 5
```

### Trend across freezes (when history exists)

```
Risk trend (4 freezes)
   This freeze:    avg 42, max 78  (okhttp)
   Previous:       avg 47, max 82  (dagger-android)
   2 freezes ago:  avg 51, max 88
   3 freezes ago:  avg 53, max 91
                                ↓ trending down — good
```

## Alternatives considered

- **Always-on risk score**: rejected — overwhelming for new users
  and not yet trustworthy as an absolute measure (see ADR-0004).
- **Single black-box score**: rejected — opacity defeats the
  purpose. The breakdown must always show how the score was
  produced.
- **Industry-specific defaults shipped in the tool**: rejected for
  the first cut — defaults are for general-purpose Android. Teams
  in regulated industries tune via config.

## Cost estimate

Small once the dependency proposals (RFC-0001, 0002, 0006, 0007,
0009) are shipped. ~2 days:

- Score computation modules per dimension
- Configuration loader for weights and thresholds
- Report rendering with breakdown bars
- Trend calculation across multiple report files

## Success metrics

- Sum of computed dimension contributions exactly equals the
  printed score (no rounding bugs)
- Default weights produce a sensible top-10 ranking on a hand-
  reviewed reference project
- Custom weights propagate correctly through the report
