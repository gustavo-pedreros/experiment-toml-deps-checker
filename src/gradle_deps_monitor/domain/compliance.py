"""Compliance — domain model for Play Store compliance findings."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ComplianceSeverity(StrEnum):
    """Severity levels for Play Store compliance findings."""

    ERROR = "error"  # Active violation: deadline already passed
    WARNING = "warning"  # Upcoming deadline within the foreseeable future
    INFO = "info"  # Compliant / informational


@dataclass(frozen=True)
class ComplianceFinding:
    """A single Play Store compliance observation.

    Attributes:
        rule_id:   Stable identifier (e.g. ``"PLAY-DEP-001"``).
        severity:  One of :class:`ComplianceSeverity`.
        message:   Short one-line description shown in reports.
        detail:    Optional longer explanation / recommendation.
        deadline:  ISO 8601 date string (``"YYYY-MM-DD"``) of the compliance
                   deadline, or ``None`` if not applicable.
        migration: Suggested replacement Maven coordinate, or ``None``.
    """

    rule_id: str
    severity: ComplianceSeverity
    message: str
    detail: str = ""
    deadline: str | None = None
    migration: str | None = None
