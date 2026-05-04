"""Rule: catalog.missing-plugins — no [plugins] section in catalog."""

from __future__ import annotations

from gradle_deps_monitor.domain.catalog import Catalog
from gradle_deps_monitor.domain.finding import Finding, Severity

ID = "catalog.missing-plugins"
SEVERITY = Severity.WARNING


def check(catalog: Catalog) -> list[Finding]:
    """Return a finding when a non-empty catalog declares no plugins."""
    has_content = catalog.library_count > 0 or len(catalog.bundles) > 0
    if catalog.plugin_count > 0 or not has_content:
        return []
    return [
        Finding(
            rule_id=ID,
            severity=SEVERITY,
            message="No [plugins] section found in catalog",
            details=(
                "Centralizing Gradle plugin versions in libs.versions.toml "
                "ensures consistent versions across all modules and enables "
                "atomic upgrades."
            ),
        )
    ]
