# ADR-0007: Tooling stack

## Status

Accepted — 2026-05-03

## Context

The Phase 1 implementation requires several technical choices:
package manager / install model, Python version floor, project
layout, linter, formatter, type checker, test framework, and CLI
framework. Each of these decisions is small in isolation, but
together they shape the contributor experience and the
maintainability of the codebase for years.

Capturing them as a single ADR keeps the rationale together. They
were chosen as a coherent set, not independently.

## Decision

The project adopts the following tooling stack:

### Package manager and install model

- **Primary**: `pipx install gradle-deps-monitor` — the de-facto
  standard for distributing Python CLIs in isolated environments
- **Secondary**: `uv tool install gradle-deps-monitor` — modern
  alternative, faster, with the same isolation semantics
- **Fallback**: `pip install gradle-deps-monitor` — documented for
  users who manage their own virtual environments

A single `pyproject.toml` supports all three; no special-casing is
required.

### Python version

**Python 3.11 or newer is required.** This unlocks:

- `tomllib` in the standard library (no `tomli` backport needed)
- Mature `asyncio.TaskGroup` semantics
- `typing.Self`, structural pattern matching, and other modern
  syntax used throughout the codebase

Python 3.11 is widely available on contemporary CI providers
including GitHub Actions and Bitrise, and on developer machines
via `pyenv`, `uv`, or system package managers.

### Project layout

The codebase uses the **`src/` layout** recommended by the Python
Packaging Authority:

```
gradle-deps-monitor/
├── pyproject.toml
├── src/
│   └── gradle_deps_monitor/
│       └── ...
├── tests/
└── docs/
```

This avoids subtle import-path bugs that occur with flat layouts
when tests run before installation, and makes the package
boundary explicit.

### Linting and formatting

**`ruff`** for both linting and formatting. A single tool replaces
`black`, `isort`, `flake8`, `pyupgrade`, and several other legacy
utilities. Ruff's speed (sub-second on this codebase) keeps pre-
commit hooks viable as the project grows.

### Tests

**`pytest`** with the standard plugins (`pytest-asyncio` for
async tests, `pytest-cov` for coverage). The `tests/` directory
mirrors the `src/` structure so each layer has its own test
package.

Test scope follows the layered architecture:

- `tests/domain/` — pure unit tests, no I/O
- `tests/application/` — use case tests with fake adapters
- `tests/infrastructure/` — integration tests, may hit the network
- `tests/checks/` — rule tests with synthetic catalogs
- `tests/e2e/` — full pipeline against fixture projects

### Type checking

**`mypy`** in strict mode for `domain/`, `application/`, and
`checks/`. Strict typing in these layers protects the core
business logic. Infrastructure may relax strictness when external
libraries lack type stubs.

### CLI framework

**`typer`** built on `click`. Type hints generate the CLI
interface, output uses `rich` for legible terminal rendering, and
the boilerplate per command is minimal.

### Architecture enforcement

**`import-linter`** runs in CI and enforces the layer contracts
declared in `pyproject.toml`. See [ADR-0006](0006-pragmatic-clean-architecture.md)
for the layer rules.

## Consequences

**Positive**

- Modern, coherent tooling with low friction for new contributors
- A single configuration file (`pyproject.toml`) hosts the entire
  stack
- Fast feedback loops: ruff in < 1s, mypy and import-linter in a
  few seconds
- Standard install model that works on every developer machine
  and CI provider

**Negative**

- Python 3.11 is a hard floor; users on Linux distributions that
  ship 3.10 must upgrade or use `pipx` / `uv` (which manage their
  own interpreter)
- `ruff` and `uv` are recent; their configuration formats may
  evolve and require occasional migrations
- `import-linter` adds a small CI step that contributors must
  understand to interpret violations
- `typer`'s magic (type-hint-driven CLI generation) hides some
  detail; debugging unusual CLI behavior occasionally requires
  understanding the underlying `click` model
