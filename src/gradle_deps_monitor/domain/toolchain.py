"""Toolchain — domain model for toolchain compatibility findings."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from gradle_deps_monitor.domain.severity import CommonSeverity


class ToolchainSeverity(StrEnum):
    """Severity levels for toolchain compatibility findings."""

    ERROR = "error"  # Incompatible combination — build may break
    WARNING = "warning"  # Likely mismatch — investigate
    INFO = "info"  # Compatible / informational

    def to_common(self) -> CommonSeverity:
        """Map this toolchain severity to the cross-section vocabulary."""
        return _TOOLCHAIN_TO_COMMON[self]


# 1:1 — toolchain vocabulary already aligns with CommonSeverity.
_TOOLCHAIN_TO_COMMON: dict[ToolchainSeverity, CommonSeverity] = {
    ToolchainSeverity.ERROR: CommonSeverity.ERROR,
    ToolchainSeverity.WARNING: CommonSeverity.WARNING,
    ToolchainSeverity.INFO: CommonSeverity.INFO,
}


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
