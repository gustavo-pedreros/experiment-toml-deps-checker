"""Port (abstract interface) for the license-audit checker.

Concrete implementations live in ``gradle_deps_monitor.infrastructure``.
"""

from __future__ import annotations

from typing import Protocol

from gradle_deps_monitor.domain.catalog import Library
from gradle_deps_monitor.domain.license import LicenseAudit


class LicenseChecker(Protocol):
    """Check the license tier of every library in the catalog.

    Implementations are expected to be async (POM fetching over HTTP)
    and to return a :class:`~gradle_deps_monitor.domain.license.LicenseAudit`
    containing only non-permissive findings.
    """

    async def check(self, libraries: tuple[Library, ...]) -> LicenseAudit:
        """Classify *libraries* by license tier.

        :param libraries: All catalog libraries to audit.
        :returns: :class:`~gradle_deps_monitor.domain.license.LicenseAudit`
            with only non-permissive findings.
        """
        ...
