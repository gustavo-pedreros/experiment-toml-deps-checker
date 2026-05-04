# RFC-0002: Play Store compliance check

**Status:** In Progress — bundled KB + deprecated library detection + targetSdk check (Step 15)
**Created:** 2026-05-03
**Related JTBDs:** JTBD-1
**Depends on:** none

## Problem

Google Play imposes recurring requirements on apps published to or
updated on the store: minimum target SDK levels (refreshed
annually), 64-bit ABI support, App Bundle format, deprecation of
specific Google SDKs (e.g., SafetyNet → Play Integrity), and
ongoing privacy / data safety obligations.

Teams discover these deadlines late, often during a freeze, when
remediation is expensive. A freeze report is the right moment to
surface upcoming compliance work.

## Proposed solution

Add a "Play Store compliance" section to the report that
synthesizes the current state of the project against Google's
published requirements.

Data sources:

- The official Google requirements page
  (https://developer.android.com/google/play/requirements/target-sdk)
  — scraped on a slow cadence (monthly), cached in the tool's
  data directory
- A small curated list of known Google SDK deprecations with
  deadlines (e.g., SafetyNet sunset)
- The project's `targetSdk`, `minSdk`, and `compileSdk` values,
  read from Gradle build files or supplied by the user via config

Example output:

```
🏛️ Play Store Compliance (data refreshed: 2026-04-15)
   ✅ Target SDK 34 (current minimum: 34, valid until 2026-08-31)
   ⚠️  Upcoming deadline: target SDK 35 required for new apps from
       2026-08-31 — 4 months remaining
   ❌ SafetyNet detected (com.google.android.gms:play-services-safetynet)
       Deprecated. Migrate to Play Integrity API before 2025-01-31.
   ✅ App Bundle (AAB) is enforced for new app uploads (already AAB)
   ✅ 64-bit ABIs supplied by Gradle defaults
```

Findings are tagged with severity:

- ❌ blocker (deadline already passed or imminent)
- ⚠️ warning (deadline in the foreseeable future)
- ✅ compliant

## Alternatives considered

- **Hardcoding deadlines into the tool**: simpler initially, but
  becomes wrong as soon as Google moves a date. Rejected.
- **Querying a third-party API for compliance data**: no reliable
  third-party source exists. Google's docs are the canonical
  reference.
- **Skipping compliance and leaving it to the team**: rejected —
  this is a high-leverage feature precisely because teams forget
  these dates.

## Cost estimate

Medium. ~2-3 days for the initial implementation:

- HTML scraper for the Google requirements page with conservative
  selectors and a pinned cache duration
- Curated YAML of known SDK deprecations (small, ships with the
  tool)
- Project metadata extraction (target / min / compile SDK)
- Report rendering

## Success metrics

- The report flags every known Google deadline within 6 months of
  the run date
- The scraper survives at least 12 months of upstream HTML changes
  without breaking — verified by a periodic CI canary
- False positives on legitimate, fully compliant projects: 0
