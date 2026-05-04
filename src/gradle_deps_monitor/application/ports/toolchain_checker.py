"""Port — toolchain compatibility checker protocol."""

from __future__ import annotations

from typing import Protocol

from gradle_deps_monitor.domain.catalog import Catalog
from gradle_deps_monitor.domain.toolchain import ToolchainFinding


class ToolchainChecker(Protocol):
    """Checks a Gradle Version Catalog for toolchain compatibility issues."""

    def check(self, catalog: Catalog) -> tuple[ToolchainFinding, ...]:
        """Return toolchain compatibility findings for *catalog*."""
        ...
