"""CommonSeverity — cross-section severity vocabulary (RFC-0016).

Each section in the report defines its own domain-specific severity enum
(``Severity`` for catalog health, ``ToolchainSeverity`` for toolchain,
``AdvisorySeverity`` for CVEs, etc.). Those local vocabularies are
deliberately kept — ``LibraryHealthSeverity.HIGH`` is not the same
concept as ``ComplianceSeverity.ERROR`` — but writers and the console
need a single dial to render them with consistent emoji, color, and
label across formats.

This module exposes:

* :class:`CommonSeverity` — the unified vocabulary used by writers.
* :class:`HasCommonSeverity` — a structural protocol that captures the
  ``to_common()`` contract every section severity satisfies. Writers
  parameterise on the protocol instead of an ever-growing union of
  concrete enum types.

The mapper methods ``to_common()`` themselves live on each
domain-specific enum so adding a new severity flavour does not force
an edit here.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol, runtime_checkable


class CommonSeverity(StrEnum):
    """Cross-section severity vocabulary used by writers and the console.

    Ordered conceptually from most to least urgent:

    * ``ERROR``      — needs immediate action.
    * ``WARNING``    — soon-to-be-urgent, watch closely.
    * ``INFO``       — informational, no action required.
    * ``SUGGESTION`` — optional improvement / nice-to-have.
    """

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
    SUGGESTION = "suggestion"


@runtime_checkable
class HasCommonSeverity(Protocol):
    """Structural contract satisfied by every section-specific severity enum.

    ``Severity``, ``ToolchainSeverity``, ``ComplianceSeverity``,
    ``LibraryHealthSeverity`` and ``AdvisorySeverity`` all implement
    ``to_common()`` and therefore satisfy this protocol. Cross-section
    consumers (writers, console renderer) parameterise on this protocol so
    that adding a new section enum does not require extending a type-union
    in every consumer signature.
    """

    def to_common(self) -> CommonSeverity:
        """Map this section-specific severity to the unified vocabulary."""
        ...
