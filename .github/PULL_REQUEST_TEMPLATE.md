## Summary

<!-- 1–3 short bullets describing what this PR does and why. -->

## RFC / ADR reference

<!--
Link the RFC and/or ADR that motivates this change. If none exists,
explain why (e.g., "trivial fix", "housekeeping", "security patch").
Significant changes should have a proposal under docs/proposals/.
-->

## Test plan

- [ ] `ruff check .`
- [ ] `ruff format --check .`
- [ ] `mypy src`
- [ ] `lint-imports`
- [ ] `pytest`

## Checklist

- [ ] Layer rules respected — no infrastructure imports from domain or
      application
- [ ] Public API changes are documented in the relevant RFC and the
      JSON schema is bumped per [ADR-0008](../docs/adr/0008-json-schema-semver.md)
- [ ] New behaviour is covered by tests
- [ ] If shipping an RFC, the proposal status was updated and the
      roadmap entry moved to ✅ in a follow-up housekeeping PR

## Notes for reviewers

<!-- Anything reviewers should pay particular attention to. -->
