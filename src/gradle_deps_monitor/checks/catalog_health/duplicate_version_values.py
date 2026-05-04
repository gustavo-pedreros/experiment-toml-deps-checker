"""Rule: catalog.duplicate-version-values — multiple version keys share the same value."""

from __future__ import annotations

from gradle_deps_monitor.domain.catalog import Catalog
from gradle_deps_monitor.domain.finding import Finding, Severity

ID = "catalog.duplicate-version-values"
SEVERITY = Severity.SUGGESTION


def check(catalog: Catalog) -> list[Finding]:
    """Return one finding per group of version keys that share the same value."""
    by_value: dict[str, list[str]] = {}
    for key, value in catalog.versions.items():
        by_value.setdefault(value, []).append(key)

    findings = []
    for version, keys in sorted(by_value.items()):
        if len(keys) < 2:
            continue
        key_list = ", ".join(sorted(keys))
        findings.append(
            Finding(
                rule_id=ID,
                severity=SEVERITY,
                message=f'Version "{version}" declared {len(keys)} times ({key_list})',
                details=(
                    "Consider consolidating under a single version key and "
                    "using version.ref across all affected entries."
                ),
            )
        )
    return findings
