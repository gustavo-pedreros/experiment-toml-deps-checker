"""Finding — result emitted by a catalog health rule."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Severity(StrEnum):
    """Severity levels for catalog health findings, ordered from most to least severe."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
    SUGGESTION = "suggestion"


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
