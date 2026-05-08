# RFC-0020: Robust Version Detection (Rich Versions Support)

**Status:** Draft
**Created:** 2026-05-07
**Related JTBDs:** JTBD-5 (report accuracy)
**Depends on:** none

## Problem

Gradle Version Catalogs support "rich versions" (objects with `strictly`, `require`, `prefer`, or `reject` keys). The current implementation of `PlayStoreComplianceChecker` and `ToolchainCompatibilityChecker` re-reads the TOML file and assumes version values are simple strings. If a version is defined as an object, it is currently ignored or causes a silent failure in detection.

## Proposed solution

Centralize version extraction and normalization in the `TomlCatalogParser`.

### Normalization Logic
Update `_resolve_version` to handle dictionary types:
- If a dictionary has a `strictly` or `require` key, use that string as the version value for technical checks.
- If it only has `reject`, mark it as unresolvable for compliance checks.

### Data Model Improvement
The `Catalog` and `Library` domain objects should carry the "effective version string" used for compatibility matrices, ensuring that downstream checkers don't need to re-parse the TOML.

## Implementation Plan

### Phase 1: Parser Refactor
- Update `infrastructure/parsing/toml_catalog_parser.py` to handle rich version dictionaries.
- Ensure `version_ref` resolution still works correctly when the referenced version is a rich object.

### Phase 2: Checker Simplification
- Remove manual TOML reading from `PlayStoreComplianceChecker` and `ToolchainCompatibilityChecker`.
- Pass the already-parsed `Catalog.versions` dictionary to these checkers.

## Alternatives considered

- **Forbid rich versions:** Rejected. These are a standard feature of Gradle catalogs and are frequently used for SDK levels and toolchain pins.
