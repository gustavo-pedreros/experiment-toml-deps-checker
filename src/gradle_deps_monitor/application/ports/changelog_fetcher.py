"""ChangelogFetcher port — outbound protocol for changelog discovery."""

from __future__ import annotations

from typing import Protocol

from gradle_deps_monitor.domain.catalog import Library
from gradle_deps_monitor.domain.changelog import ChangelogEntry


class ChangelogFetcher(Protocol):
    """Outbound port: discover changelog information for libraries with major upgrades.

    Implementations query Maven registries for the latest stable version,
    identify libraries where ``latest_major > pinned_major``, then attempt
    to retrieve release notes via the GitHub Releases API or a CHANGELOG.md
    fallback.

    Only libraries with a confirmed major upgrade available produce a
    :class:`~gradle_deps_monitor.domain.changelog.ChangelogEntry`.
    """

    async def fetch(self, libraries: tuple[Library, ...]) -> tuple[ChangelogEntry, ...]:
        """Return changelog entries for libraries with a major version upgrade.

        :param libraries: All libraries from the parsed catalog.
        :returns: One entry per library where ``latest_stable_major > pinned_major``.
            Libraries without an upgrade or where the latest version could not
            be determined are omitted.
        """
        ...
