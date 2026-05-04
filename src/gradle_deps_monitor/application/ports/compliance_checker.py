"""ComplianceChecker — port for Play Store compliance checks."""

from __future__ import annotations

from typing import Protocol

from gradle_deps_monitor.domain.catalog import Catalog
from gradle_deps_monitor.domain.compliance import ComplianceFinding


class ComplianceChecker(Protocol):
    """Checks a catalog against Play Store compliance requirements.

    Implementations may inspect library coordinates, SDK version aliases in
    the TOML source file, and any other catalog metadata they need.
    """

    def check(self, catalog: Catalog) -> tuple[ComplianceFinding, ...]:
        """Return compliance findings for *catalog*.

        An empty tuple means the catalog is fully compliant with all
        checked requirements.
        """
        ...
