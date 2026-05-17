"""ChangelogFetcher port — outbound protocol for changelog discovery."""

from __future__ import annotations

from typing import Protocol

from gradle_deps_monitor.domain.catalog import Library
from gradle_deps_monitor.domain.changelog import ChangelogEntry, ChangelogFetchStats


class ChangelogFetcher(Protocol):
    """Outbound port: discover changelog information for libraries with major upgrades.

    Implementations query Maven registries for the latest stable version,
    identify libraries where ``latest_major > pinned_major``, then attempt
    to retrieve release notes via the GitHub Releases API or a CHANGELOG.md
    fallback.

    Only libraries with a confirmed major upgrade available produce a
    :class:`~gradle_deps_monitor.domain.changelog.ChangelogEntry`.

    RFC-0024 PR #2: implementations also return a
    :class:`~gradle_deps_monitor.domain.changelog.ChangelogFetchStats`
    summarising per-library outcomes so the presentation layer can
    surface silent degradation (notably GitHub rate-limit exhaustion).
    """

    async def fetch(
        self, libraries: tuple[Library, ...]
    ) -> tuple[tuple[ChangelogEntry, ...], ChangelogFetchStats]:
        """Return changelog entries + per-fetch stats.

        :param libraries: All libraries from the parsed catalog.
        :returns: ``(entries, stats)`` where ``entries`` has one entry per
            library with ``latest_stable_major > pinned_major`` (libraries
            without an upgrade or where the latest version could not be
            determined are omitted), and ``stats`` summarises classifier
            outcomes for the attempted libraries.
        """
        ...
