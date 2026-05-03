# ADR-0006: Pragmatic Clean Architecture for the Python CLI

## Status

Accepted — 2026-05-03

## Context

The tool will grow significantly across four roadmap phases, with
multiple integrations on both the input side (Maven Central, Google
Maven, GitHub Advisory Database, OSS Index, future registries and
matrices) and the output side (Markdown, JSON, Slack Block Kit,
future HTML). The codebase will receive contributions from open-
source authors who must be able to extend it without rewriting the
core.

A flat module structure would make these extensions risky:
infrastructure concerns (HTTP clients, file I/O, third-party
APIs) would leak into business logic, tests would require live
network access, and the cost of swapping a registry or adding an
output format would scale with the size of the codebase.

Canonical Clean Architecture as practiced in Java / Kotlin imposes
ceremony that is not idiomatic in Python (DI containers,
interfaces declared up front for every collaborator, layered DTOs
between every boundary). The goal is to capture the structural
benefits without importing the ceremony.

## Decision

The codebase is organized into the following layers, with strict
dependency rules enforced by `import-linter` in CI:

```
domain         ← imports from no one
   ↑
application    ← imports from domain only
   ↑
checks         ← imports from domain only
   ↑
infrastructure ← imports from domain and application (implements ports)
   ↑
presentation   ← imports from application (never from infrastructure)
   ↑
bootstrap      ← the only module aware of all layers
```

Layer responsibilities:

- **domain** — value objects and aggregates. No I/O, no
  frameworks. Examples: `MavenVersion`, `Library`,
  `VersionCatalog`, `Vulnerability`, `RiskScore`, `Finding`,
  `FreezeReport` (aggregate root).
- **application** — use cases that orchestrate the domain.
  Defines `Protocol` interfaces (ports) for outbound dependencies.
  Examples: `GenerateFreezeReport`, `ScanVulnerabilities`,
  `CompareFreezes`.
- **checks** — pluggable rules (catalog health, deprecations).
  Each rule is a self-contained module discovered at runtime.
  Held outside `application` because rules are extension points,
  not core orchestration.
- **infrastructure** — concrete adapters. Maven / Google /
  GitHub clients, TOML parser, cache, output writers. Implements
  the ports declared in `application/ports/`.
- **presentation** — the CLI delivery mechanism (Typer commands,
  Rich console rendering). Never reaches into infrastructure
  directly.
- **bootstrap** — the composition root. The only module that
  imports from every layer to wire concrete implementations into
  use cases.

### Pythonic adaptations to canonical Clean Architecture

The following relaxations are intentional, to keep the codebase
idiomatic and avoid Java-style ceremony:

- **Protocols, not abstract interfaces.** Use `typing.Protocol`
  (PEP 544) for ports. Structural typing avoids declaring an
  interface separately from its implementation when there is only
  one concrete adapter.
- **No DI framework.** Constructor injection by hand. The
  composition root in `bootstrap.py` wires dependencies. Python's
  dynamic typing makes a framework unnecessary.
- **Functions over classes when stateless.** A use case with no
  collaborators is a function. A class is introduced only when
  state or injected dependencies justify it.
- **Domain entities as DTOs.** No separate DTO layer between
  domain and application. View models exist only at the output
  boundary (Markdown / JSON / Slack), where each format imposes
  distinct constraints.
- **Protocols introduced on demand.** A `Protocol` is added when
  there are at least two implementations or when a fake is needed
  for tests. Speculative interfaces "for future flexibility" are
  not added.
- **Plug-in `checks/` outside the layer hierarchy.** Catalog
  health and deprecation rules are independent extension points.
  Each rule imports from `domain` and emits `Finding` objects.

### Enforcement

Layer rules are enforced via `import-linter` configured in
`pyproject.toml`. CI fails any PR that violates a contract.

The contracts encode:

- `domain` cannot import from any other internal package
- `application` cannot import from `infrastructure` or
  `presentation`
- `presentation` cannot import from `infrastructure`
- `checks` cannot import from `infrastructure`, `presentation`,
  or `application`
- `bootstrap` is the sole exception with permission to import
  from any layer

## Consequences

**Positive**

- Fast unit tests for the domain (no I/O, milliseconds per test)
- Adding a new registry, output format, or rule is a single new
  file in the appropriate layer
- Test fakes are trivial because ports are explicit
- Contributors have an obvious place to put new code
- Architectural drift is caught automatically by `import-linter`

**Negative**

- More files than a flat layout would have (~3-5x in some cases)
- Newcomers familiar with single-file Python tools may face a
  small initial learning curve
- The composition root grows over time; periodic refactors of
  `bootstrap.py` will be needed to keep it readable
- Strict layer enforcement occasionally rejects pragmatic
  shortcuts; the team must update contracts deliberately rather
  than disabling them
