"""Catalog health runner — collects and executes all built-in rules."""

from __future__ import annotations

from gradle_deps_monitor.checks.catalog_health import (
    duplicate_library,
    duplicate_version_values,
    inconsistent_naming,
    inline_versions,
    missing_bundles,
    missing_plugins,
    orphan_version_ref,
    unresolved_bom_child,
    unresolved_version_ref,
)
from gradle_deps_monitor.domain.catalog import Catalog
from gradle_deps_monitor.domain.finding import Finding

# Order: errors first, then warnings, then info, then suggestions.
_RULES = [
    duplicate_library,
    unresolved_version_ref,
    unresolved_bom_child,
    inconsistent_naming,
    missing_plugins,
    orphan_version_ref,
    inline_versions,
    missing_bundles,
    duplicate_version_values,
]


def run_all(catalog: Catalog) -> tuple[Finding, ...]:
    """Run all built-in catalog health rules and return every finding.

    Satisfies the :class:`~gradle_deps_monitor.application.ports.health_checker.HealthChecker`
    Protocol so it can be injected directly without a wrapper class.

    :param catalog: The parsed :class:`~gradle_deps_monitor.domain.catalog.Catalog`.
    :returns: Tuple of :class:`~gradle_deps_monitor.domain.finding.Finding` objects
        (may be empty when the catalog is clean).
    """
    findings: list[Finding] = []
    for rule in _RULES:
        findings.extend(rule.check(catalog))
    return tuple(findings)
