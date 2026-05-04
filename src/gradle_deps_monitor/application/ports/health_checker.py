"""HealthChecker port — callable that audits a Catalog and returns findings."""

from __future__ import annotations

from typing import Protocol

from gradle_deps_monitor.domain.catalog import Catalog
from gradle_deps_monitor.domain.finding import Finding


class HealthChecker(Protocol):
    """Outbound port: run catalog health rules and return all findings.

    Implemented as a callable so that a plain function (e.g.
    ``checks.runner.run_all``) satisfies the protocol without wrapping.
    """

    def __call__(self, catalog: Catalog) -> tuple[Finding, ...]:
        """Audit *catalog* and return all health findings (may be empty)."""
        ...
