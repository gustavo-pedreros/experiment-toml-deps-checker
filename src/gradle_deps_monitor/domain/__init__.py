"""Domain layer.

Pure value objects and aggregates. No I/O, no frameworks. May not import from
any other layer of the project.
"""

from gradle_deps_monitor.domain.advisory import Advisory, AdvisorySeverity, LibraryAdvisory
from gradle_deps_monitor.domain.catalog import Bundle, Catalog, Library, Plugin
from gradle_deps_monitor.domain.finding import Finding, Severity
from gradle_deps_monitor.domain.report import FreezeReport
from gradle_deps_monitor.domain.rich_version import RichVersion
from gradle_deps_monitor.domain.version import MavenVersion, Stability

__all__ = [
    "Advisory",
    "AdvisorySeverity",
    "Bundle",
    "Catalog",
    "Finding",
    "FreezeReport",
    "Library",
    "LibraryAdvisory",
    "MavenVersion",
    "Plugin",
    "RichVersion",
    "Severity",
    "Stability",
]
