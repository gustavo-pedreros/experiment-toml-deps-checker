"""Library health — domain model for library deprecation and inactivity findings."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from gradle_deps_monitor.domain.severity import CommonSeverity


class LibraryHealthSeverity(StrEnum):
    """Severity levels for library health findings."""

    HIGH = "high"  # Officially deprecated or relocated
    MEDIUM = "medium"  # Inactive (24-36 months without a release)
    LOW = "low"  # Minor concern (reserved for future signals)

    def to_common(self) -> CommonSeverity:
        """Map this library-health severity to the cross-section vocabulary.

        ``HIGH`` (deprecated/relocated) becomes :class:`CommonSeverity.ERROR`
        because the library has reached end-of-life. ``MEDIUM`` (inactive)
        becomes :class:`CommonSeverity.WARNING` — the library may not have
        new releases but it still works. ``LOW`` is informational.
        """
        return _HEALTH_TO_COMMON[self]


_HEALTH_TO_COMMON: dict[LibraryHealthSeverity, CommonSeverity] = {
    LibraryHealthSeverity.HIGH: CommonSeverity.ERROR,
    LibraryHealthSeverity.MEDIUM: CommonSeverity.WARNING,
    LibraryHealthSeverity.LOW: CommonSeverity.INFO,
}


class HealthSignal(StrEnum):
    """The detection mechanism that produced a finding."""

    CURATED = "curated"  # Matched an entry in the bundled knowledge base
    RELOCATED = "relocated"  # POM ``<relocation>`` tag detected on Maven Central
    INACTIVE = "inactive"  # No Maven release in 24+ months (heuristic)


@dataclass(frozen=True)
class LibraryHealthFinding:
    """A single library-level health observation.

    Attributes:
        alias:              Catalog alias (e.g. ``"butterknife"``).
        coordinate:         Maven coordinate ``"group:artifact"``.
        version:            Pinned version string.
        signal:             Which detection mechanism fired.
        severity:           One of :class:`LibraryHealthSeverity`.
        message:            Short one-line description for reports.
        replacement:        Suggested replacement coordinate or description,
                            or ``None`` if no known successor exists.
        migration_url:      Link to an official migration guide, or ``None``.
        days_since_release: Days since the last published release (inactivity
                            signal only), or ``None`` for other signals.
    """

    alias: str
    coordinate: str
    version: str
    signal: HealthSignal
    severity: LibraryHealthSeverity
    message: str
    replacement: str | None = None
    migration_url: str | None = None
    days_since_release: int | None = None
