"""Unit tests for the central SeverityStyle map (RFC-0016)."""

from __future__ import annotations

import pytest

from gradle_deps_monitor.domain.severity import CommonSeverity
from gradle_deps_monitor.domain.severity_style import (
    STYLE,
    SeverityStyle,
    style_for,
)


class TestStyleMap:
    def test_every_common_severity_has_a_style(self) -> None:
        """STYLE must cover every CommonSeverity — gap = KeyError at runtime."""
        for sev in CommonSeverity:
            assert sev in STYLE

    def test_no_extra_entries(self) -> None:
        """STYLE entries map 1:1 to CommonSeverity values."""
        assert set(STYLE.keys()) == set(CommonSeverity)

    @pytest.mark.parametrize("sev", list(CommonSeverity))
    def test_all_fields_are_non_empty(self, sev: CommonSeverity) -> None:
        s = STYLE[sev]
        assert s.label.strip() != ""
        assert s.rich_style.strip() != ""
        assert s.md_emoji.strip() != ""
        assert s.slack_emoji.startswith(":") and s.slack_emoji.endswith(":")

    def test_labels_are_short(self) -> None:
        """Labels stay ≤ 5 chars to keep table column widths predictable."""
        for sev, style in STYLE.items():
            assert len(style.label) <= 5, f"{sev}: {style.label!r}"

    def test_labels_are_uppercase(self) -> None:
        for sev, style in STYLE.items():
            assert style.label.isupper(), f"{sev}: {style.label!r}"


class TestStyleFor:
    def test_returns_corresponding_style(self) -> None:
        assert style_for(CommonSeverity.ERROR) is STYLE[CommonSeverity.ERROR]

    def test_returns_seveirty_style_instance(self) -> None:
        assert isinstance(style_for(CommonSeverity.WARNING), SeverityStyle)


class TestExpectedRendering:
    """Lock-in tests so 16b can rely on these conventions."""

    def test_error_is_red(self) -> None:
        assert STYLE[CommonSeverity.ERROR].rich_style == "bold red"
        assert STYLE[CommonSeverity.ERROR].md_emoji == "🔴"
        assert STYLE[CommonSeverity.ERROR].slack_emoji == ":red_circle:"

    def test_warning_is_yellow(self) -> None:
        assert STYLE[CommonSeverity.WARNING].rich_style == "bold yellow"
        assert STYLE[CommonSeverity.WARNING].slack_emoji == ":warning:"

    def test_info_is_neutral(self) -> None:
        # INFO is intentionally NOT red/yellow so it doesn't compete with
        # ERROR / WARNING in a skim test.
        assert "red" not in STYLE[CommonSeverity.INFO].rich_style
        assert "yellow" not in STYLE[CommonSeverity.INFO].rich_style

    def test_suggestion_is_dim(self) -> None:
        assert "dim" in STYLE[CommonSeverity.SUGGESTION].rich_style
        assert STYLE[CommonSeverity.SUGGESTION].label == "TIP"
