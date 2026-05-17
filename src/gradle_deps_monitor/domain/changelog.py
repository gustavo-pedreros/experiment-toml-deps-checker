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


@dataclass(frozen=True)
class ChangelogFetchStats:
    """Per-fetch counters describing how the scrape pass classified each library.

    Used by the presentation layer to surface silent degradation (notably
    GitHub rate-limit exhaustion) that would otherwise just look like
    ``BreakingSignal.UNKNOWN`` entries with bare repo URLs. RFC-0024 PR #2.

    Counter semantics — exactly one of ``fetched``, ``fallback_url_only``,
    ``rate_limited``, ``unknown_no_repo`` increments per attempted library:

    - ``attempted``:         libraries with a candidate major upgrade.
    - ``fetched``:           got release notes body + URL successfully.
    - ``fallback_url_only``: GitHub repo found but no release notes
                             retrieved; entry carries the bare repo URL.
    - ``rate_limited``:      at least one request in the per-library
                             pipeline returned a documented rate-limit
                             response (HTTP 429, or 403 with
                             ``X-RateLimit-Remaining: 0``).
    - ``unknown_no_repo``:   POM had no SCM URL or the SCM URL didn't
                             resolve to a GitHub repository.

    Default-constructed instance has all counters at zero — used when no
    scraping ran (no major upgrades, scraper disabled, etc.).
    """

    attempted: int = 0
    fetched: int = 0
    fallback_url_only: int = 0
    rate_limited: int = 0
    unknown_no_repo: int = 0

    @property
    def is_degraded(self) -> bool:
        """``True`` when at least one library's outcome was rate-limited.

        Drives the warning banner in the console and Markdown reports.
        """
        return self.rate_limited > 0
