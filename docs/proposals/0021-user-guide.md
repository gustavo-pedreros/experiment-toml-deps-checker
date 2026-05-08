# RFC-0021: Official User Guide

**Status:** Draft
**Created:** 2026-05-07
**Related JTBDs:** JTBD-5 (readability), onboarding
**Depends on:** none

## Problem

The project lacks official user-facing documentation. While a draft `USER_GUIDE.md` exists in some environments, it is not part of the repository's core docs, is written in Spanish (violating ADR-0005), and contains outdated information about "limitations" (like BoM support) that were resolved in Phase 4.

## Proposed solution

Create a comprehensive, official `docs/USER_GUIDE.md` in English that reflects the current state of the tool and provides clear onboarding for Android teams.

### Content Outline

1.  **Introduction:** Purpose of the tool and technical due-diligence.
2.  **Core Commands:**
    *   `check`: Deep audit and reporting.
    *   `diff`: Baseline establishment and comparative analysis.
3.  **Advanced Features:**
    *   Risk Score (weights and thresholds).
    *   Module Usage Map (opt-in).
    *   Maven BoM support.
4.  **CI Integration:**
    *   GitHub Actions example.
    *   Bitrise example.
    *   Slack notification setup.
5.  **Configuration:**
    *   `gradle-deps-monitor.toml` reference.
    *   Environment variables (tokens).

## Implementation Plan

### Phase 1: Drafting
- Write the full guide in English.
- Verify all CLI examples against the actual help output.

### Phase 2: Integration
- Move the guide to `docs/USER_GUIDE.md`.
- Update `README.md` with a "Documentation" section pointing to the guide.
- Remove the unofficial/untracked `USER_GUIDE.md` from the root (if present).

## Alternatives considered

- **In-README documentation:** Rejected. The README should be a high-level overview. A separate guide is better for deep-dives and CI examples.
