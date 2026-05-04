"""Toolchain — domain model for toolchain compatibility findings."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ToolchainSeverity(StrEnum):
    """Severity levels for toolchain compatibility findings."""

    ERROR = "error"  # Incompatible combination — build may break
    WARNING = "warning"  # Likely mismatch — investigate
    INFO = "info"  # Compatible / informational


@dataclass(frozen=True)
class ToolchainFinding:
    """A single toolchain compatibility observation.

    Attributes:
        rule_id:        Stable identifier (e.g. ``"TOOL-KC-001"``).
        severity:       One of :class:`ToolchainSeverity`.
        message:        Short one-line description shown in reports.
        detail:         Optional longer explanation.
        recommendation: Suggested action to resolve the finding.
    """

    rule_id: str
    severity: ToolchainSeverity
    message: str
    detail: str = ""
    recommendation: str = ""
