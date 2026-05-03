# RFC-0009: License audit

**Status:** Proposed
**Created:** 2026-05-03
**Related JTBDs:** JTBD-2
**Depends on:** none

## Problem

A commercial app may unintentionally pull in dependencies under
licenses incompatible with its distribution model (GPL, AGPL).
Discovering this late — during a legal review or app-store audit —
is expensive.

The freeze report is the right moment to surface a license audit.

## Proposed solution

For each dependency, extract the license from its POM file
(`<licenses><license><name>` and `<url>`). Classify each license
into a risk tier:

- **Permissive** (Apache 2.0, MIT, BSD): no restrictions for
  commercial closed-source distribution
- **Weak copyleft** (LGPL, MPL): allows linking; restrictions
  apply to modifications
- **Strong copyleft** (GPL, AGPL): typically incompatible with
  closed-source commercial distribution
- **Unknown**: license could not be determined

Configurable per project: which tiers are acceptable.

```toml
[license_policy]
allowed_tiers = ["permissive", "weak_copyleft"]
fail_on_unknown = false
exceptions = [
  # group:artifact pairs explicitly approved despite their tier
]
```

Output section:

```
⚖️ License audit
   ❌ org.example:gpl-library 1.0.0
       License: GPL-3.0-or-later (strong copyleft)
       Action: review with legal before next release

   ⚠️  com.example:no-license-info 2.1.0
       License: not declared in POM
       Action: verify license at the source repository

   ✅ All other dependencies (284) are under permissive licenses.
```

## Alternatives considered

- **Skip the audit, leave it to legal review**: rejected — by
  the time legal sees it, the dependency is integrated. Surfacing
  this at freeze time is preventive.
- **Use a third-party SBOM service**: heavy, often paid, adds an
  external dependency for what is essentially a POM field read.
- **Extract licenses via Gradle plugin**: more accurate (resolves
  transitive deps) but requires running Gradle. May be added later
  as an opt-in mode.

## Cost estimate

Small. ~1-2 days:

- License extraction from POMs (extends existing POM fetcher)
- License normalization (SPDX identifiers where possible)
- Tier classifier with a curated mapping
- Configurable policy loader
- Report rendering

## Success metrics

- A test fixture with known GPL, MIT, Apache 2.0, and missing-
  license dependencies classifies each one correctly
- The audit completes in negligible additional time (POMs are
  already being fetched for other features)
- False positive rate on well-known permissively-licensed
  Android dependencies: 0%
