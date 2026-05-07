"""Compliance — domain model for Play Store compliance findings."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from gradle_deps_monitor.domain.severity import CommonSeverity


class ComplianceSeverity(StrEnum):
    """Severity levels for Play Store compliance findings."""

    ERROR = "error"  # Active violation: deadline already passed
    WARNING = "warning"  # Upcoming deadline within the foreseeable future
    INFO = "info"  # Compliant / informational

    def to_common(self) -> CommonSeverity:
        """Map this compliance severity to the cross-section vocabulary."""
        return _COMPLIANCE_TO_COMMON[self]


# 1:1 — compliance vocabulary already aligns with CommonSeverity.
_COMPLIANCE_TO_COMMON: dict[ComplianceSeverity, CommonSeverity] = {
    ComplianceSeverity.ERROR: CommonSeverity.ERROR,
    ComplianceSeverity.WARNING: CommonSeverity.WARNING,
    ComplianceSeverity.INFO: CommonSeverity.INFO,
}


@dataclass(frozen=True)
class ComplianceFinding:
    """A single Play Store compliance observation.

    Attributes:
        rule_id:    Stable identifier (e.g. ``"PLAY-DEP-001"``).
        severity:   One of :class:`ComplianceSeverity`.
        message:    Short one-line description shown in reports.
        detail:     Optional longer explanation / recommendation.
        deadline:   ISO 8601 date string (``"YYYY-MM-DD"``) of the compliance
                    deadline, or ``None`` if not applicable.
        migration:  Suggested replacement Maven coordinate, or ``None``.
        alias:      Catalog alias when the finding concerns a specific library
                    (e.g. ``"safetynet"``). ``None`` for catalog-level findings
                    such as ``targetSdk`` requirements. Added by RFC-0015.
        coordinate: ``group:artifact`` mirror of *alias*. ``None`` for
                    catalog-level findings. Added by RFC-0015.
    """

    rule_id: str
    severity: ComplianceSeverity
    message: str
    detail: str = ""
    deadline: str | None = None
    migration: str | None = None
    alias: str | None = None
    coordinate: str | None = None
