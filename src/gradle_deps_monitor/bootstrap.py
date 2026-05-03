"""Composition root.

Wires concrete adapters (infrastructure) into use cases (application). This is
the only module permitted to import from every layer; see
``docs/adr/0006-pragmatic-clean-architecture.md`` and the import-linter
contracts in ``pyproject.toml``.

Phase 1 work in progress: builders will be added here as infrastructure
adapters land.
"""
