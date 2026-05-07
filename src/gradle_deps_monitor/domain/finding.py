"""Finding — result emitted by a catalog health rule."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from gradle_deps_monitor.domain.severity import CommonSeverity


class Severity(StrEnum):
    """Severity levels for catalog health findings, ordered from most to least severe."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
    SUGGESTION = "suggestion"

    def to_common(self) -> CommonSeverity:
        """Map this catalog-health severity to the cross-section vocabulary."""
        return _CATALOG_TO_COMMON[self]


# 1:1 mapping — catalog health was the original blueprint for CommonSeverity.
_CATALOG_TO_COMMON: dict[Severity, CommonSeverity] = {
    Severity.ERROR: CommonSeverity.ERROR,
    Severity.WARNING: CommonSeverity.WARNING,
    Severity.INFO: CommonSeverity.INFO,
    Severity.SUGGESTION: CommonSeverity.SUGGESTION,
}


@dataclass(frozen=True)
class Finding:
    """A single catalog health observation produced by a rule.

    Attributes:
        rule_id:  Stable identifier (e.g. ``"catalog.inline-versions"``).
        severity: One of :class:`Severity`.
        message:  Short one-line description shown in reports.
        details:  Optional longer explanation / recommendation.
    """

    rule_id: str
    severity: Severity
    message: str
    details: str = ""
