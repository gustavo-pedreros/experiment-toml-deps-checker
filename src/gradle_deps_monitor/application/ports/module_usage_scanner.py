"""Port: ModuleUsageScanner.

Implemented by concrete infrastructure adapters (e.g.
:class:`~...infrastructure.scanners.gradle_module_scanner.GradleModuleScanner`).
Injected into :class:`~...application.generate_freeze_report.GenerateFreezeReport`
at construction time.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from gradle_deps_monitor.domain.catalog import Catalog
from gradle_deps_monitor.domain.module_usage import ModuleUsageMap


class ModuleUsageScanner(Protocol):
    """Scan Gradle build files and return a module usage map.

    :param catalog_path: The path passed to the CLI — either the directory
        containing ``libs.versions.toml`` or the file itself.  The scanner
        uses this as the starting point to locate ``settings.gradle(.kts)``.
    :param catalog: The already-parsed version catalog used for alias lookup.
    :returns: A :class:`ModuleUsageMap`, or ``None`` when the project root /
        settings file cannot be found (e.g. the catalog is not inside a Gradle
        project tree).
    """

    def scan(self, catalog_path: Path, catalog: Catalog) -> ModuleUsageMap | None: ...
