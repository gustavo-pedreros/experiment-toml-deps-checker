"""BomResolver port — outbound protocol for RFC-0014.

A :class:`BomResolver` takes the BoM library entries identified in a
catalog and returns a :class:`~gradle_deps_monitor.domain.bom.BomResolution`
per BoM. The use case then walks the catalog's other libraries and,
for any whose pinned version is empty, fills it in from the matching
BoM resolution.
"""

from __future__ import annotations

from typing import Protocol

from gradle_deps_monitor.domain.bom import BomResolution
from gradle_deps_monitor.domain.catalog import Library


class BomResolver(Protocol):
    """Outbound port: resolve catalog BoM entries to their managed dependency sets."""

    async def resolve(self, boms: tuple[Library, ...]) -> tuple[BomResolution, ...]:
        """Return one :class:`BomResolution` per resolvable BoM, in input order.

        Implementations MUST swallow per-BoM errors (network failures,
        malformed POMs) and skip the affected BoM rather than aborting
        the whole resolution.
        """
        ...
