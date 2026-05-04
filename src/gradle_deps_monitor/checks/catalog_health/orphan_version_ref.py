"""Rule: catalog.orphan-version-ref — version key declared but never referenced."""

from __future__ import annotations

from gradle_deps_monitor.domain.catalog import Catalog
from gradle_deps_monitor.domain.finding import Finding, Severity

ID = "catalog.orphan-version-ref"
SEVERITY = Severity.WARNING


def check(catalog: Catalog) -> list[Finding]:
    """Return a finding listing version keys that no library or plugin references."""
    referenced = {lib.version_ref for lib in catalog.libraries if lib.version_ref is not None} | {
        p.version_ref for p in catalog.plugins if p.version_ref is not None
    }

    orphans = sorted(k for k in catalog.versions if k not in referenced)
    if not orphans:
        return []

    orphan_list = ", ".join(orphans)
    return [
        Finding(
            rule_id=ID,
            severity=SEVERITY,
            message=f"{len(orphans)} orphan version key(s): {orphan_list}",
            details=(
                "These version keys are declared in [versions] but never "
                "referenced via version.ref. Remove them to keep the catalog clean."
            ),
        )
    ]
