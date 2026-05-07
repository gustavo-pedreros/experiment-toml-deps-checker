"""Rule: catalog.unresolved-bom-child — library has no version and no BoM resolved it.

After [RFC-0014](docs/proposals/0014-maven-bom-support.md) BoM
enrichment runs, every library should either:

- carry an inline literal version (``LITERAL``), or
- reference a ``[versions]`` entry (``VERSION_REF``), or
- have its version supplied by a resolved BoM (``FROM_BOM``).

Any library that ends up in :attr:`VersionSource.UNRESOLVED` after the
pipeline ran is an orphan: typically the catalog declared it without a
version on the assumption that a BoM would manage it, but the BoM was
removed (or fails to resolve). This rule fires loudly so the freeze
review catches the regression.

Rule ID: ``HDX-009`` (legacy ID kept for parity with the existing
HDX-* numbering used by other rules in this directory).
"""

from __future__ import annotations

from gradle_deps_monitor.domain.bom import VersionSource
from gradle_deps_monitor.domain.catalog import Catalog
from gradle_deps_monitor.domain.finding import Finding, Severity

ID = "catalog.unresolved-bom-child"
SEVERITY = Severity.ERROR


def check(catalog: Catalog) -> list[Finding]:
    """Return one Finding per library whose version is still UNRESOLVED."""
    orphans = [
        lib.alias for lib in catalog.libraries if lib.version_source == VersionSource.UNRESOLVED
    ]
    if not orphans:
        return []

    entry_list = ", ".join(orphans)
    return [
        Finding(
            rule_id=ID,
            severity=SEVERITY,
            message=(f"{len(orphans)} library(ies) have no version and no BoM resolves them"),
            details=(
                "Orphans (declared without a version, no managing BoM found): "
                f"{entry_list}. Either add a version, point to a [versions] entry, "
                "or restore the BoM that managed them."
            ),
        )
    ]
