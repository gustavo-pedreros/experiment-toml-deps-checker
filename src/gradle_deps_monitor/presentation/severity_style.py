"""SeverityStyle — central style mapping for cross-section rendering (RFC-0016a).

Each :class:`~gradle_deps_monitor.domain.severity.CommonSeverity` value resolves
to a single :class:`SeverityStyle` that describes how it should render in:

* the Rich console (``rich_style``),
* Markdown (``md_emoji`` + ``label``),
* Slack Block Kit (``slack_emoji`` + ``label``).

Sections used to embed their own dictionaries (``_TOOLCHAIN_STYLE``,
``_COMPLIANCE_SEVERITY_ICON``, etc.); RFC-0016b will retire those in favour of
this module so the same finding severity renders identically everywhere.

This module is purely additive — it does not yet replace any existing style
constants. Wiring lives in 16b.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from gradle_deps_monitor.domain.severity import CommonSeverity


@dataclass(frozen=True)
class SeverityStyle:
    """Visual representation of a :class:`CommonSeverity` across formats.

    Attributes:
        label:        Short uppercase string for tables and table-like rows
                      (max 4 characters: ``ERROR``/``WARN``/``INFO``/``TIP``
                      keep column widths predictable). The exception is
                      ``ERROR`` which is 5 chars; treat it as the upper bound.
        rich_style:   Rich style markup (e.g. ``"bold red"``) used by the
                      console renderer.
        md_emoji:     Single emoji shown next to the severity label in
                      Markdown tables. Chosen for legibility on both light
                      and dark backgrounds.
        slack_emoji:  Slack ``:colon-emoji:`` shortcode (e.g.
                      ``":red_circle:"``).
    """

    label: str
    rich_style: str
    md_emoji: str
    slack_emoji: str


# Single source of truth for severity rendering. Adding a new severity to
# CommonSeverity requires adding an entry here — the runtime lookup helpers
# raise :class:`KeyError` otherwise so the gap is caught immediately.
STYLE: Final[dict[CommonSeverity, SeverityStyle]] = {
    CommonSeverity.ERROR: SeverityStyle(
        label="ERROR",
        rich_style="bold red",
        md_emoji="🔴",
        slack_emoji=":red_circle:",
    ),
    CommonSeverity.WARNING: SeverityStyle(
        label="WARN",
        rich_style="bold yellow",
        md_emoji="🟡",
        slack_emoji=":warning:",
    ),
    CommonSeverity.INFO: SeverityStyle(
        label="INFO",
        rich_style="cyan",
        md_emoji="🔵",
        slack_emoji=":information_source:",
    ),
    CommonSeverity.SUGGESTION: SeverityStyle(
        label="TIP",
        rich_style="dim",
        md_emoji="💡",
        slack_emoji=":bulb:",
    ),
}


def style_for(severity: CommonSeverity) -> SeverityStyle:
    """Return the :class:`SeverityStyle` for *severity*.

    Thin lookup helper that raises :class:`KeyError` if a CommonSeverity value
    is added without a matching style entry.
    """
    return STYLE[severity]
