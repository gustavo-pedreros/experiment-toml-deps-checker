"""CommonSeverity — cross-section severity vocabulary (RFC-0016).

Each section in the report defines its own domain-specific severity enum
(``Severity`` for catalog health, ``ToolchainSeverity`` for toolchain,
``AdvisorySeverity`` for CVEs, etc.). Those local vocabularies are
deliberately kept — ``LibraryHealthSeverity.HIGH`` is not the same
concept as ``ComplianceSeverity.ERROR`` — but the *presentation* layer
needs a single dial to render them with consistent emoji, color, and
label across console, Markdown, and Slack.

This module exposes:

* :class:`CommonSeverity` — the unified vocabulary used by writers.
* The mapper methods ``to_common()`` live on each domain-specific enum
  so adding a new severity flavour does not force an edit here.

Per the RFC, this module is purely additive: existing enums keep their
identity and existing writers keep working until RFC-0016b refactors
them to use :mod:`gradle_deps_monitor.presentation.severity_style`.
"""

from __future__ import annotations

from enum import StrEnum


class CommonSeverity(StrEnum):
    """Cross-section severity vocabulary used by presentation.

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
