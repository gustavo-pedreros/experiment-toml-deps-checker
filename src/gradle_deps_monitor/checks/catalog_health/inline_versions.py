"""Rule: catalog.inline-versions — version literals instead of version.ref."""

from __future__ import annotations

from gradle_deps_monitor.domain.catalog import Catalog
from gradle_deps_monitor.domain.finding import Finding, Severity

ID = "catalog.inline-versions"
SEVERITY = Severity.INFO


def check(catalog: Catalog) -> list[Finding]:
    """Return a finding listing all entries with inline (non-ref) versions."""
    inline = [
        lib.alias for lib in catalog.libraries if lib.version_ref is None and str(lib.version)
    ] + [p.alias for p in catalog.plugins if p.version_ref is None and str(p.version)]

    if not inline:
        return []

    count = len(inline)
    examples = ", ".join(inline[:3])
    suffix = f" and {count - 3} more" if count > 3 else ""
    return [
        Finding(
            rule_id=ID,
            severity=SEVERITY,
            message=f"{count} inline version(s) detected",
            details=(
                f"Examples: {examples}{suffix}. "
                "Using version.ref shares a single version key across related "
                "libraries, preventing drift between sibling artifacts."
            ),
        )
    ]
