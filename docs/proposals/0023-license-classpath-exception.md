# RFC-0023: License Classifier — GPL with Classpath Exception

**Status:** Proposed
**Created:** 2026-05-16
**Related JTBDs:** JTBD-2 (compliance / legal), JTBD-5 (report accuracy)
**Depends on:** RFC-0009 (License Audit)

## Problem

The current license classifier (`pom_license_checker._classify_license`)
treats every license string containing the keyword ``gpl`` as
:attr:`LicenseTier.STRONG_COPYLEFT` once LGPL has been ruled out. This
is too coarse: it false-positives on the **GPL family with Classpath
Exception (CPE)**, which is functionally permissive for application
linking.

The Classpath Exception is a specific carve-out attached to GPL v2 (most
notably by OpenJDK) that says *linking the licensed code into a larger
work does not subject that larger work to the GPL*. It exists precisely
so that Java applications and Android apps can depend on OpenJDK-derived
libraries without becoming GPL themselves. Treating GPL+CPE as Strong
Copyleft alongside vanilla GPL contradicts the exception's purpose.

**Concrete observation from real-world validation.** Running the tool
against a fintech-style multi-module Android project surfaced
``com.android.tools:desugar_jdk_libs`` (Google's official desugaring
library) flagged as:

```
🔴 Strong Copyleft  desugaring  GNU General Public License, version 2,
                                with the Classpath Exception
```

A reviewer skimming this finding could reasonably conclude the library
needs to be removed — but doing so would break every project targeting
API < 26 that relies on Java 8+ APIs. The library is mandatory tooling
shipped by Google with the explicit guidance that the Classpath
Exception makes it safe to use in closed-source apps. The classifier
is **actively misleading** in this case.

The same false positive applies to any GPL+CPE artifact in the wild —
older Sun / Oracle Java libraries, some `javax.*` reference
implementations, and downstream packages that re-publish OpenJDK code.

## Proposed solution

Add a pre-check in `_classify_license` that detects the Classpath
Exception qualifier **before** the GPL keyword check fires, and
downgrades the result to `LicenseTier.PERMISSIVE`.

```python
# Order matters in pom_license_checker.py:
# CPE check → LGPL/weak check → strong check → permissive → unknown.
_CLASSPATH_EXCEPTION_KEYWORDS: tuple[str, ...] = (
    "classpath exception",
    "with classpath",          # covers SPDX-style "GPL-2.0 WITH Classpath-exception-2.0"
    "classpath-exception",
)

def _classify_license(name, url):
    text = f"{name or ''} {url or ''}".lower()
    if not text.strip():
        return LicenseTier.UNKNOWN

    # RFC-0023: GPL with Classpath Exception is functionally permissive
    # for application linking. Detect BEFORE the GPL keyword check fires.
    if any(kw in text for kw in _CLASSPATH_EXCEPTION_KEYWORDS):
        return LicenseTier.PERMISSIVE

    # ...existing checks unchanged
```

This mirrors the existing precedent of checking LGPL before GPL: the
classifier already understands that "more specific qualifier wins over
broader keyword". Classpath Exception is the same shape of refinement.

### Why PERMISSIVE and not a new tier

Three options were considered:

- **PERMISSIVE** (chosen). Matches the practical reality for app
  developers — the CPE removes the linking restriction that motivates
  STRONG_COPYLEFT in the first place. No schema change. Affected
  libraries silently disappear from the License Audit findings table
  (consistent with how other permissive libraries are filtered).
- **New `PERMISSIVE_WITH_EXCEPTION` tier**. More legally precise (the
  source code itself is still GPL; only the linking is exempted). But
  this adds a new `LicenseTier` enum value, requiring a MINOR schema
  bump per ADR-0008, plus rendering decisions across all four writers
  (Markdown, JSON, Slack, console). The marginal benefit is small for
  practical app development; we can introduce this later if a real
  user need surfaces.
- **Keep STRONG_COPYLEFT but annotate**. Confuses the risk score
  (already capped at 5 by license tier) and leaves the noisy finding
  in place. Rejected on UX grounds.

## Tracer Bullet Path (ADR-0009)

The fix is small enough that the entire change *is* the tracer: one
new keyword tuple, one extra `if` block, and the tests that pin both
the new behaviour and the existing GPL/LGPL guards. The tracer step
within the PR is:

1. **Infrastructure:** add `_CLASSPATH_EXCEPTION_KEYWORDS` constant
   adjacent to the other keyword tuples in
   `pom_license_checker.py`; insert the pre-check in
   `_classify_license` immediately after the empty-text guard.
2. **Composition Root:** no wiring change — `PomLicenseChecker` is
   already registered in `bootstrap.py`.
3. **Minimal Output:** a `TestClassifyLicense` case covering the
   full-name form ("GNU General Public License, version 2, with the
   Classpath Exception") returns `LicenseTier.PERMISSIVE` instead of
   `STRONG_COPYLEFT`.

That single test is the regression target: the bug, the fix, and the
guard against future regression all collapse onto it.

## Implementation Plan

### PR #1 — Detect Classpath Exception + tests + CHANGELOG

Single PR, two commits:

**Commit 1 — `docs(rfc-0023)`: proposal + Phase 6 entry**
- New `docs/proposals/0023-license-classpath-exception.md` (this
  file).
- New `docs/proposals/README.md` index row.
- New `docs/roadmap.md` Phase 6 row for RFC-0023.

**Commit 2 — `fix(rfc-0023)`: treat GPL with Classpath Exception as permissive + CHANGELOG**
- `_CLASSPATH_EXCEPTION_KEYWORDS` tuple added to
  `pom_license_checker.py`.
- Pre-check inserted in `_classify_license` ahead of the existing
  weak/strong/permissive cascade.
- Six new unit tests in `TestClassifyLicense`:
  - Full prose form ("GNU General Public License, version 2, with the
    Classpath Exception") → PERMISSIVE.
  - SPDX expression form ("GPL-2.0 WITH Classpath-exception-2.0") →
    PERMISSIVE.
  - URL-based detection (license URL contains the qualifier, name
    empty) → PERMISSIVE.
  - Mixed case input → PERMISSIVE (regression for `.lower()`).
  - Vanilla "GPL-2.0" (no qualifier) → STRONG_COPYLEFT (negative test,
    pins that the pre-check doesn't over-trigger).
  - Vanilla "LGPL-3.0" → WEAK_COPYLEFT (regression for the existing
    cascade; pre-check must not interfere).
- CHANGELOG entry under `[Unreleased] / Fixed` describing the bug,
  the symptom, and the resolution with credit to RFC-0023.

## Alternatives considered

- **Hard-code `com.android.tools:desugar_jdk_libs` as an exemption.**
  Rejected — would only fix the one observed case; other GPL+CPE
  artifacts (older `javax.*` reference implementations, OpenJDK
  derivatives) would still false-positive.
- **Drop the GPL keyword entirely from `_STRONG_COPYLEFT_KEYWORDS`.**
  Rejected — vanilla GPL is genuinely strong copyleft; suppressing the
  signal there would create a much worse false-negative for any
  library actually licensed under unmodified GPL.
- **Pre-check after the weak/strong cascade and re-classify.**
  Possible but more confusing — the cascade would briefly assign
  STRONG_COPYLEFT and then we'd reverse it. A clean pre-check is
  easier to read and easier to test.
- **Use a real SPDX expression parser (e.g.
  `python-license-expression`).** Rejected — pulls in a transitive
  dependency for a keyword match that fits in three tuple entries.
  Reconsider only if more nuanced SPDX expressions (`OR` / `AND`
  combinators, exception modifiers beyond CPE) become a recurring
  need.

## Cost estimate

Trivial. One file edit in `pom_license_checker.py` (+~8 LoC), one new
keyword tuple, six new unit tests in
`tests/infrastructure/checkers/test_pom_license_checker.py`. No new
dependencies. No network call changes. No schema migration.

## Success metrics

- **`desugar_jdk_libs` in the validation corpus**: previously appeared
  as the lone 🔴 Strong Copyleft finding in the License Audit table;
  after the fix it disappears from the findings table (filtered out as
  PERMISSIVE, consistent with the existing behaviour for other
  permissive libraries). The "Strong Copyleft" count in the License
  Audit summary drops by 1.
- **Risk score license dimension**: any library whose only finding was
  the false-positive STRONG_COPYLEFT loses the corresponding 3-of-5
  license-tier points (the dimension's max), since the library is now
  reclassified as PERMISSIVE.
- **No regression**: every existing test in
  `tests/infrastructure/checkers/test_pom_license_checker.py` passes
  unmodified.

## Schema impact

`none`. Outputs change only in *which* libraries appear under
"Strong Copyleft" vs the implicit permissive bucket. The shape of
`license_audit.findings[]` in `freeze.json` is unchanged. Consumers
reading `1.x` will see one fewer entry per affected GPL+CPE library
on the next run — semantically equivalent to upstream re-licensing.

## Rollback strategy

Revert the single PR → classifier reverts to flagging GPL+CPE
libraries as STRONG_COPYLEFT. No cache invalidation required
(`PomLicenseChecker` has no on-disk cache; results are recomputed per
run from the POM XML). No JSON schema changes, so downstream
consumers see the affected library re-appear under
`license_audit.findings[]` on the next run after revert.

## PR budget

Estimated **1 PR** (two commits). The change is small enough that
splitting into multiple PRs would add ceremony without lowering risk.

## Definition of Done (DoD)

- [ ] **Integration:** `_CLASSPATH_EXCEPTION_KEYWORDS` pre-check is in
  place in `_classify_license`; no wiring change needed in
  `bootstrap.py`.
- [ ] **Architecture:** Follows ADR-0006 (Clean Architecture) and
  ADR-0009 (Tracer Bullets).
- [ ] **Accuracy — positive cases:** Unit tests verify
  `_classify_license` returns PERMISSIVE for the full prose form,
  the SPDX expression form, the URL-only form, and mixed-case input.
- [ ] **Accuracy — negative cases:** Unit tests verify vanilla GPL
  still returns STRONG_COPYLEFT and vanilla LGPL still returns
  WEAK_COPYLEFT.
- [ ] **No regression:** All existing tests in
  `tests/infrastructure/checkers/test_pom_license_checker.py` pass
  unmodified.
- [ ] **Documentation:** CHANGELOG entry under `[Unreleased] / Fixed`
  credits RFC-0023 and describes the symptom + fix.
