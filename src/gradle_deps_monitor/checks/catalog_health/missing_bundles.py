"""Rule: catalog.missing-bundles — no [bundles] section in a multi-library catalog."""

from __future__ import annotations

from gradle_deps_monitor.domain.catalog import Catalog
from gradle_deps_monitor.domain.finding import Finding, Severity

ID = "catalog.missing-bundles"
SEVERITY = Severity.INFO

# Only suggest bundles when there are enough libraries to benefit from grouping.
_MIN_LIBRARIES = 2


def check(catalog: Catalog) -> list[Finding]:
    """Return a finding when a multi-library catalog defines no bundles."""
    if len(catalog.bundles) > 0 or catalog.library_count < _MIN_LIBRARIES:
        return []
    return [
        Finding(
            rule_id=ID,
            severity=SEVERITY,
            message="No [bundles] section found",
            details=(
                f"Your catalog declares {catalog.library_count} libraries. "
                "Bundles group related libraries so build files reference a "
                "single alias instead of listing each dependency individually."
            ),
        )
    ]
