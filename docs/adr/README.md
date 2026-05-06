# Architecture Decision Records

ADRs capture decisions that have already been accepted and that
constrain how the project is built. They are short, retrospective,
and numbered sequentially.

The format follows Michael Nygard's original template.

## When to write an ADR

Write an ADR when a decision:

- Closes off a design alternative
- Constrains future implementation choices
- Would be expensive to reverse
- Would require explanation to a new contributor reading the code

Decisions that are too small for an ADR (variable naming, minor
refactors) are captured in commit messages and PR descriptions.

## Template

```markdown
# ADR-NNNN: Short title

## Status

Accepted | Superseded by ADR-XXXX | Deprecated

## Context

What is the situation that requires a decision? What forces are at
play? What constraints exist? Keep this section short — 1 to 3
paragraphs.

## Decision

What did we decide? State it directly, in the present tense.

## Consequences

What becomes easier? What becomes harder? What did we trade away?
List both positive and negative consequences honestly.
```

## Index

- [ADR-0001](0001-python-over-bash.md) — Python as the single language
- [ADR-0002](0002-markdown-as-canonical-output-format.md) — Markdown as the canonical report format
- [ADR-0003](0003-bundled-plus-remote-deprecation-kb.md) — Bundled plus remote distribution for the deprecation knowledge base
- [ADR-0004](0004-risk-score-opt-in-with-disclaimer.md) — Risk score is opt-in by default and shipped with a refinement disclaimer
- [ADR-0005](0005-language-convention-english-in-repo.md) — Repo content is in English regardless of contributor language
- [ADR-0006](0006-pragmatic-clean-architecture.md) — Pragmatic Clean Architecture for the Python CLI
- [ADR-0007](0007-tooling-stack.md) — Tooling stack (Python 3.11+, ruff, pytest, mypy, typer, pipx/uv)
- [ADR-0008](0008-json-schema-semver.md) — JSON output `schema_version` follows SemVer (`x.y.z`)
