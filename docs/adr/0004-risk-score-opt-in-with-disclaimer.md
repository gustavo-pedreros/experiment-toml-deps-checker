# ADR-0004: Risk score is opt-in by default and shipped with a refinement disclaimer

## Status

Accepted — 2026-05-03

## Context

The risk score (see [RFC-0008](../proposals/0008-risk-score.md))
combines several dimensions — outdatedness, CVE severity,
abandonment, blast radius, compliance pressure, license risk — into
a single 0-100 number per dependency.

Two concerns shaped the decision:

- **Cognitive load.** A composite score with six inputs is harder
  to interpret than a single dimension. Users running the tool for
  the first time benefit from a simpler, more direct report.
- **Maturity of the indicator.** A composite score becomes
  meaningful only when interpreted across multiple freeze reports
  (a trend), and only when its weights have been tuned to the
  team's context. Showing it prominently from day one risks
  misinterpretation.

## Decision

The risk score is **off by default**. Users opt in via a CLI flag
(`--risk-score`) or a configuration setting (`features.risk_score
= true`).

When enabled, the report includes:

1. An explanatory section that defines what the score is, how it is
   computed, and how to tune the weights for the team's context
2. A disclaimer marking the indicator as **experimental** and
   noting that single-freeze values are less informative than
   trends across multiple freezes
3. A per-dependency breakdown showing the contribution of each
   dimension, so the score is never opaque

Weights and thresholds are configurable via `config.toml`. Defaults
are calibrated for general-purpose Android applications. Teams in
regulated industries (fintech, health) typically increase the
weights for `cve` and `license`.

## Consequences

**Positive**

- New users get a simpler report by default; the score does not
  overwhelm
- Teams that want the score get a transparent, tunable indicator
- Teams in regulated contexts can express their priorities without
  forking
- The "experimental" framing manages expectations until the
  indicator has trend data to support it

**Negative**

- Two reporting modes (with and without the score) increase the
  surface area of the output
- The configuration system has to support per-feature weight
  overrides, which is a small but real complexity cost
- The benefit of the score is delayed until enough freeze history
  exists to interpret trends; users who enable it on day one may
  underrate it
