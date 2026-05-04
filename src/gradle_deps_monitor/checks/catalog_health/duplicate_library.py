"""Rule: catalog.duplicate-library — same group:artifact declared more than once."""

from __future__ import annotations

from gradle_deps_monitor.domain.catalog import Catalog
from gradle_deps_monitor.domain.finding import Finding, Severity

ID = "catalog.duplicate-library"
SEVERITY = Severity.ERROR


def check(catalog: Catalog) -> list[Finding]:
    """Return one finding per group:artifact pair declared under multiple aliases."""
    seen: dict[tuple[str, str], list[str]] = {}
    for lib in catalog.libraries:
        key = (lib.group, lib.artifact)
        seen.setdefault(key, []).append(lib.alias)

    findings = []
    for (group, artifact), aliases in sorted(seen.items()):
        if len(aliases) < 2:
            continue
        alias_list = ", ".join(sorted(aliases))
        findings.append(
            Finding(
                rule_id=ID,
                severity=SEVERITY,
                message=f"Duplicate library {group}:{artifact} ({alias_list})",
                details=(
                    "Multiple aliases point to the same artifact. Remove duplicates "
                    "to prevent version drift between aliases."
                ),
            )
        )
    return findings
