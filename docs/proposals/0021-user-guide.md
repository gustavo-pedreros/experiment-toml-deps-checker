# RFC-0021: Official User Guide

**Status:** In progress (Phase 1 shipped 2026-05-18; Phase 2/3 pending)
**Created:** 2026-05-07
**Related JTBDs:** JTBD-5 (Readability), Onboarding
**Depends on:** none

## Problem

The project lacks official, up-to-date, and unified documentation for end users. The existing information is scattered across READMEs and RFCs, and the untracked `USER_GUIDE.md` is in Spanish (violating ADR-0005) and contains technical inaccuracies regarding recently shipped features (like BoM support).

## Proposed solution

Deliver a comprehensive `docs/USER_GUIDE.md` in English that serves as the "Technical Manual" for Android teams.

### 1. Scope
- **Getting Started**: Installation, project structure, and first run.
- **Feature Deep-Dives**: Detailed explanation of Risk Score, Module Usage, and BoM support.
- **CI Integration**: Copy-pasteable examples for GitHub Actions and Bitrise.
- **Configuration**: Complete reference for `gradle-deps-monitor.toml` and environment variables.

## Tracer Bullet Path (ADR-0009)

While this is a documentation task, it must be "integrated" into the project structure:
1. **Documentation**: Create a skeletal `docs/USER_GUIDE.md` with just the Introduction and Table of Contents.
2. **Project Index**: Link to the guide from `README.md`.
3. **Cleanup**: Remove any legacy or untracked `USER_GUIDE.md` files from the root to avoid confusion.

*This confirms the documentation "plumbing" is correct and discoverable by users.*

## Implementation Plan

### Phase 1: Tracer Bullet & Cleanup ✅ shipped 2026-05-18
- [x] Create the skeletal guide at `docs/user-guide/`:
  `index.md` (TOC + intro) + `getting-started.md` (install, first
  run, console summary, credentials, opt-in flags, exit codes).
- [x] Link from `README.md` Documentation section.
- [x] No legacy `USER_GUIDE.md` files exist at repo root —
  cleanup step was a no-op.
- *Note:* moved from a single `docs/USER_GUIDE.md` to a
  `docs/user-guide/` directory so Phase 2 chapters can land as
  separate files without rewriting the index.

### Phase 2: Content Drafting (next PR)
- Write the core sections (Configuration, Feature Deep-Dives,
  Troubleshooting).
- Verify all CLI flags against the actual implementation
  (post-RFC-0029 + RFC-0018 surface).

### Phase 3: CI Examples (folded into Phase 2 per plan)
- Add tested examples for GitHub Actions and Bitrise — driven by
  the RFC-0018 v1 exit-code contract and the `GITHUB_ACTIONS`
  annotation emitter that already ships.

## Alternatives considered

- **External Documentation Site**: Rejected for now. Keeping it in-repo (`.md`) is better for versioning and offline access.

## Success metrics

- A user can set up the tool in a new project in under 5 minutes using the guide.
- The guide covers 100% of the features described in the README.
- Zero Spanish text remains in the documentation.

## Definition of Done (DoD)

- [ ] **Content**: Full English guide covering all major features.
- [ ] **Discoverability**: Clearly linked from the main README.
- [ ] **Accuracy**: All code snippets and CLI flags are verified to be correct.
- [ ] **Cleanup**: No duplicate or legacy documentation files remain in the root.
