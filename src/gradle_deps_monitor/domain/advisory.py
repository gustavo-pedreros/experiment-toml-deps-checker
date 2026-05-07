"""Advisory — domain model for security vulnerability advisories."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from gradle_deps_monitor.domain.severity import CommonSeverity


class AdvisorySeverity(StrEnum):
    """Severity levels for security advisories, ordered from most to least severe."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"

    def to_common(self) -> CommonSeverity:
        """Map this advisory severity to the cross-section vocabulary.

        ``CRITICAL`` and ``HIGH`` both render as :class:`CommonSeverity.ERROR`
        because either is enough to block a release. ``MEDIUM`` is a
        :class:`CommonSeverity.WARNING`. ``LOW`` and ``UNKNOWN`` collapse to
        :class:`CommonSeverity.INFO` — they show up in reports but should not
        out-shout louder findings.
        """
        return _ADVISORY_TO_COMMON[self]


_ADVISORY_TO_COMMON: dict[AdvisorySeverity, CommonSeverity] = {
    AdvisorySeverity.CRITICAL: CommonSeverity.ERROR,
    AdvisorySeverity.HIGH: CommonSeverity.ERROR,
    AdvisorySeverity.MEDIUM: CommonSeverity.WARNING,
    AdvisorySeverity.LOW: CommonSeverity.INFO,
    AdvisorySeverity.UNKNOWN: CommonSeverity.INFO,
}


# Ordered for comparison (index 0 = most severe).
_SEVERITY_ORDER: tuple[AdvisorySeverity, ...] = (
    AdvisorySeverity.CRITICAL,
    AdvisorySeverity.HIGH,
    AdvisorySeverity.MEDIUM,
    AdvisorySeverity.LOW,
    AdvisorySeverity.UNKNOWN,
)


@dataclass(frozen=True)
class Advisory:
    """A single security advisory that affects a Maven library.

    Attributes:
        ghsa_id:       GitHub Security Advisory ID (e.g. ``"GHSA-xxxx-yyyy-zzzz"``).
                       May be empty for advisories sourced from OSS Index only.
        cve_id:        Common Vulnerabilities and Exposures identifier
                       (e.g. ``"CVE-2023-3635"``). May be ``None`` if not assigned.
        severity:      Classified severity level.
        summary:       Short one-line description of the vulnerability.
        fixed_version: First version that resolves the vulnerability, or ``None``
                       if no fix is available.
        url:           Canonical URL for the advisory details.
        source:        Data source identifier (e.g. ``"github"`` or ``"oss_index"``).
    """

    ghsa_id: str
    cve_id: str | None
    severity: AdvisorySeverity
    summary: str
    fixed_version: str | None
    url: str
    source: str


@dataclass(frozen=True)
class LibraryAdvisory:
    """Security advisories for a specific library version.

    Attributes:
        alias:      Catalog alias of the library.
        coordinate: Maven coordinate in ``group:artifact`` form.
        version:    The version present in the catalog.
        advisories: Advisories that affect this version (may be empty).
    """

    alias: str
    coordinate: str
    version: str
    advisories: tuple[Advisory, ...]

    @property
    def is_vulnerable(self) -> bool:
        """``True`` when at least one advisory affects this version."""
        return len(self.advisories) > 0

    @property
    def max_severity(self) -> AdvisorySeverity | None:
        """The highest severity among all advisories, or ``None`` if there are none."""
        if not self.advisories:
            return None
        for sev in _SEVERITY_ORDER:
            if any(a.severity == sev for a in self.advisories):
                return sev
        return None  # pragma: no cover

    @property
    def has_critical(self) -> bool:
        """``True`` when at least one advisory is CRITICAL severity."""
        return any(a.severity == AdvisorySeverity.CRITICAL for a in self.advisories)

    @property
    def has_high(self) -> bool:
        """``True`` when at least one advisory is HIGH severity."""
        return any(a.severity == AdvisorySeverity.HIGH for a in self.advisories)
