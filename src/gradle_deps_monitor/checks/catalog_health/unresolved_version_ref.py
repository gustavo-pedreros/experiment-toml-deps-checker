"""Rule: catalog.unresolved-version-ref — version.ref points to missing key.

Note: the TOML parser already rejects catalogs with unresolved refs by raising
``CatalogParseError``. This rule therefore acts as a guard for ``Catalog``
objects constructed directly (e.g. in tests) without going through the parser.
It will always return no findings for catalogs produced by ``TomlCatalogParser``.
"""

from __future__ import annotations

from gradle_deps_monitor.domain.catalog import Catalog
from gradle_deps_monitor.domain.finding import Finding, Severity

ID = "catalog.unresolved-version-ref"
SEVERITY = Severity.ERROR


def check(catalog: Catalog) -> list[Finding]:
    """Return findings for every version.ref that has no matching [versions] key."""
    unresolved = []
    for lib in catalog.libraries:
        if lib.version_ref is not None and lib.version_ref not in catalog.versions:
            unresolved.append(f"{lib.alias} (ref: {lib.version_ref})")
    for plugin in catalog.plugins:
        if plugin.version_ref is not None and plugin.version_ref not in catalog.versions:
            unresolved.append(f"{plugin.alias} (ref: {plugin.version_ref})")

    if not unresolved:
        return []

    entry_list = ", ".join(unresolved)
    return [
        Finding(
            rule_id=ID,
            severity=SEVERITY,
            message=f"{len(unresolved)} unresolved version ref(s)",
            details=f"Entries with missing refs: {entry_list}",
        )
    ]
