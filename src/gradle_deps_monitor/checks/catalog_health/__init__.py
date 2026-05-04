"""Built-in catalog health rules.

Each sub-module exposes ``ID``, ``SEVERITY``, and ``check(catalog) -> list[Finding]``.
"""

from gradle_deps_monitor.checks.catalog_health import (
    duplicate_library,
    duplicate_version_values,
    inconsistent_naming,
    inline_versions,
    missing_bundles,
    missing_plugins,
    orphan_version_ref,
    unresolved_version_ref,
)

__all__ = [
    "duplicate_library",
    "duplicate_version_values",
    "inconsistent_naming",
    "inline_versions",
    "missing_bundles",
    "missing_plugins",
    "orphan_version_ref",
    "unresolved_version_ref",
]
