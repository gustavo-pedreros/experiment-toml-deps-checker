"""Domain layer.

Pure value objects and aggregates. No I/O, no frameworks. May not import from
any other layer of the project.
"""

from gradle_deps_monitor.domain.catalog import Bundle, Catalog, Library, Plugin
from gradle_deps_monitor.domain.report import FreezeReport
from gradle_deps_monitor.domain.version import MavenVersion, Stability

__all__ = [
    "Bundle",
    "Catalog",
    "FreezeReport",
    "Library",
    "MavenVersion",
    "Plugin",
    "Stability",
]
