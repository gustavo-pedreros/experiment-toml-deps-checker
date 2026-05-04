"""CompositeScanner — fans out to multiple scanners and merges results."""

from __future__ import annotations

import asyncio

from gradle_deps_monitor.application.ports.vulnerability_scanner import VulnerabilityScanner
from gradle_deps_monitor.domain.advisory import Advisory, LibraryAdvisory
from gradle_deps_monitor.domain.catalog import Library


class CompositeScanner:
    """Aggregates results from one or more :class:`VulnerabilityScanner` adapters.

    Scanners are queried **concurrently** via :func:`asyncio.gather`.
    Advisories from all sources are merged per-library, then deduplicated:

    - Advisories sharing the same ``cve_id`` (when not ``None``) are collapsed
      into one — the advisory with a ``fixed_version`` is preferred; otherwise
      the first seen is kept.
    - Non-CVE advisories are deduplicated by ``ghsa_id`` with the same rule.

    :param scanners: One or more scanner adapters.  When the tuple is empty,
                     :meth:`scan` returns entries with no advisories.
    """

    def __init__(self, scanners: tuple[VulnerabilityScanner, ...]) -> None:
        self._scanners = scanners

    async def scan(self, libraries: tuple[Library, ...]) -> tuple[LibraryAdvisory, ...]:
        """Return merged, deduplicated advisories for every library.

        :raises VulnerabilityScanError: Propagated from any scanner on error.
        """
        if not self._scanners:
            return tuple(
                LibraryAdvisory(
                    alias=lib.alias,
                    coordinate=f"{lib.group}:{lib.artifact}",
                    version=str(lib.version),
                    advisories=(),
                )
                for lib in libraries
            )

        # Run all scanners concurrently.
        all_results: list[tuple[LibraryAdvisory, ...]] = await asyncio.gather(
            *[scanner.scan(libraries) for scanner in self._scanners]
        )

        # Merge per-library across all scanners (results are in the same order as input).
        return tuple(
            _merge_library_results(
                lib,
                [scanner_results[i] for scanner_results in all_results],
            )
            for i, lib in enumerate(libraries)
        )


# ---------------------------------------------------------------------------
# Merge helpers
# ---------------------------------------------------------------------------


def _merge_library_results(
    lib: Library,
    per_scanner: list[LibraryAdvisory],
) -> LibraryAdvisory:
    """Merge and deduplicate advisories for *lib* from multiple scanners."""
    combined: list[Advisory] = []
    for la in per_scanner:
        combined.extend(la.advisories)

    return LibraryAdvisory(
        alias=lib.alias,
        coordinate=f"{lib.group}:{lib.artifact}",
        version=str(lib.version),
        advisories=tuple(_deduplicate(combined)),
    )


def _deduplicate(advisories: list[Advisory]) -> list[Advisory]:
    """Return *advisories* with duplicates removed.

    Two advisories are considered duplicates when they share the same CVE ID
    (``cve_id``, non-``None``) or, for non-CVE advisories, the same
    ``ghsa_id``.  Among duplicates, the advisory that has a ``fixed_version``
    set is preferred; otherwise the first occurrence is kept.
    """
    seen_cve: dict[str, Advisory] = {}
    seen_id: dict[str, Advisory] = {}
    result: list[Advisory] = []

    for adv in advisories:
        if adv.cve_id:
            existing = seen_cve.get(adv.cve_id)
            if existing is None:
                seen_cve[adv.cve_id] = adv
                result.append(adv)
            elif adv.fixed_version and not existing.fixed_version:
                # Upgrade to the advisory that carries a fixed_version.
                idx = result.index(existing)
                result[idx] = adv
                seen_cve[adv.cve_id] = adv
        else:
            existing_by_id = seen_id.get(adv.ghsa_id)
            if existing_by_id is None:
                seen_id[adv.ghsa_id] = adv
                result.append(adv)
            elif adv.fixed_version and not existing_by_id.fixed_version:
                idx = result.index(existing_by_id)
                result[idx] = adv
                seen_id[adv.ghsa_id] = adv

    return result
