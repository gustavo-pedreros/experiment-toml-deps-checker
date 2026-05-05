"""Changelog — domain model for major upgrade changelog entries."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class BreakingSignal(StrEnum):
    """Indicates whether breaking changes were detected in the release notes.

    Values:
        LIKELY:  Breaking-change keywords found in the retrieved content.
        CLEAN:   Release notes found but no breaking keywords detected.
        UNKNOWN: No release notes content could be retrieved.
    """

    LIKELY = "likely"
    CLEAN = "clean"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ChangelogEntry:
    """A major upgrade opportunity with optional changelog information.

    Produced by :class:`~...infrastructure.fetchers.changelog_fetcher.ChangelogFetcher`
    for every library where ``latest_stable_major > pinned_major``.

    Attributes:
        alias:           Catalog alias (e.g. ``"retrofit"``).
        coordinate:      Maven coordinate ``"group:artifact"``.
        pinned_version:  Version currently pinned in the catalog.
        latest_version:  Latest stable version available on Maven.
        changelog_url:   Direct link to the GitHub release or changelog page,
                         or ``None`` when discovery failed.
        breaking_signal: Whether breaking changes are likely in the upgrade.
        snippet:         Short excerpt from the release notes (≤ 200 chars),
                         or ``None`` when no content was retrieved.
    """

    alias: str
    coordinate: str
    pinned_version: str
    latest_version: str
    changelog_url: str | None = None
    breaking_signal: BreakingSignal = BreakingSignal.UNKNOWN
    snippet: str | None = None
