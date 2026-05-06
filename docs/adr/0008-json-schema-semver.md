# ADR-0008: JSON output `schema_version` follows SemVer (`x.y.z`)

## Status

Accepted — 2026-05-06

## Context

The `freeze.json` report (and, separately, the `freeze-diff.json`
report) currently exposes a top-level `schema_version: 1` integer.
Throughout Phases 2 and 3, several feature RFCs added new top-level
sections (`security`, `compliance`, `toolchain`, `library_health`,
`changelog_entries`, `module_usage`, `license_audit`, `risk_score`)
without bumping the version field. Consumers cannot distinguish
additive changes from breaking ones, and there is no documented
rule that says they should be safe to ignore unknown fields.

A handful of choices were available:

- Keep the integer and bump only on breaking changes.
- Switch to SemVer (`x.y.z`) and bump per change category.
- Use date-based versioning.
- Drop the version field altogether.

The project itself is pre-1.0 (`pyproject.toml` declares `0.1.0`
at the time of this ADR), but schema-vs-tool versioning are
independent concerns: the schema can be `1.0.0` even while the
tool stays `0.x`.

## Decision

The `schema_version` field becomes a **string** following SemVer
`x.y.z`:

- **MAJOR (`x.0.0`)** — breaking changes:
  - Removed or renamed top-level keys
  - Changed types of existing fields
  - Changed semantics of existing fields (same key, different
    meaning)
- **MINOR (`1.x.0`)** — additive, backwards-compatible changes:
  - New top-level sections
  - New fields on existing objects
  - New optional values in enums
  Consumers reading version `1.x` MUST be able to process version
  `1.x+n` provided they ignore unknown fields and unknown enum
  values.
- **PATCH (`1.0.x`)** — strictly internal, wire-format-equivalent
  changes (typo fixes in field descriptions, internal precision
  changes that round-trip identically). Practically rare; most
  changes will be MINOR or MAJOR.

The same rule applies independently to the `freeze-diff.json`
schema; each schema bumps on its own cadence.

The first commit applying this ADR migrates `schema_version` from
the integer `1` to the string `"1.0.0"` in `freeze.json` and
`"1.0.0"` in `freeze-diff.json`. This single transition is the
last "breaking" change made without bumping MAJOR — it is
acceptable because the tool has no public consumers yet.

## Consequences

- Future RFCs declare the schema-version impact in their
  "Cost estimate" or "Success metrics" section. RFC-0014
  (Maven BoM) and RFC-0015 (compliance per-library
  attribution) ship as MINOR bumps under this ADR.
- The README's "Files written" table documents
  `schema_version` semantics so consumers know the contract.
- Tooling that parses `freeze.json` should read
  `schema_version` as a string and parse it via standard
  SemVer libraries (or a simple regex split).
- Bumping MAJOR is a deliberate, RFC-level decision — never a
  side-effect of an implementation PR.

## Related

- [ADR-0002](0002-markdown-as-canonical-output-format.md) —
  Markdown is the canonical format; JSON is the
  machine-readable companion.
- [RFC-0014](../proposals/0014-maven-bom-support.md) — first
  consumer of the MINOR bump rule (`1.0.0` → `1.1.0`).
- [RFC-0015](../proposals/0015-compliance-per-library-attribution.md)
  — additional MINOR bump (`1.x.0` → `1.x+1.0`).
- [RFC-0016](../proposals/0016-unified-report-style.md) — adds
  `common_severity` to existing finding objects (MINOR).
