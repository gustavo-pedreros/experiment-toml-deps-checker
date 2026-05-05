"""Unit tests for gradle_deps_monitor.domain.changelog."""

from __future__ import annotations

import pytest

from gradle_deps_monitor.domain.changelog import BreakingSignal, ChangelogEntry


class TestBreakingSignal:
    def test_values(self) -> None:
        assert BreakingSignal.LIKELY == "likely"
        assert BreakingSignal.CLEAN == "clean"
        assert BreakingSignal.UNKNOWN == "unknown"

    def test_upper(self) -> None:
        assert BreakingSignal.LIKELY.upper() == "LIKELY"


class TestChangelogEntry:
    def _make(self, **kwargs) -> ChangelogEntry:  # type: ignore[no-untyped-def]
        defaults: dict = {
            "alias": "retrofit",
            "coordinate": "com.squareup.retrofit2:retrofit",
            "pinned_version": "2.9.0",
            "latest_version": "3.0.0",
        }
        defaults.update(kwargs)
        return ChangelogEntry(**defaults)  # type: ignore[arg-type]

    def test_minimal_fields(self) -> None:
        e = self._make()
        assert e.alias == "retrofit"
        assert e.coordinate == "com.squareup.retrofit2:retrofit"
        assert e.pinned_version == "2.9.0"
        assert e.latest_version == "3.0.0"

    def test_optional_fields_default(self) -> None:
        e = self._make()
        assert e.changelog_url is None
        assert e.breaking_signal == BreakingSignal.UNKNOWN
        assert e.snippet is None

    def test_optional_fields_set(self) -> None:
        e = self._make(
            changelog_url="https://github.com/square/retrofit/releases/tag/v3.0.0",
            breaking_signal=BreakingSignal.LIKELY,
            snippet="Breaking changes in interceptors",
        )
        assert e.changelog_url is not None
        assert e.breaking_signal == BreakingSignal.LIKELY
        assert e.snippet == "Breaking changes in interceptors"

    def test_frozen(self) -> None:
        e = self._make()
        with pytest.raises(AttributeError):
            e.alias = "other"  # type: ignore[misc]

    def test_clean_entry(self) -> None:
        e = self._make(breaking_signal=BreakingSignal.CLEAN)
        assert e.breaking_signal == BreakingSignal.CLEAN
