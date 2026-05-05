"""Unit tests for gradle_deps_monitor.domain.library_health."""

from __future__ import annotations

import pytest

from gradle_deps_monitor.domain.library_health import (
    HealthSignal,
    LibraryHealthFinding,
    LibraryHealthSeverity,
)


class TestHealthSignal:
    def test_values(self) -> None:
        assert HealthSignal.CURATED == "curated"
        assert HealthSignal.RELOCATED == "relocated"
        assert HealthSignal.INACTIVE == "inactive"

    def test_upper(self) -> None:
        assert HealthSignal.CURATED.upper() == "CURATED"


class TestLibraryHealthSeverity:
    def test_values(self) -> None:
        assert LibraryHealthSeverity.HIGH == "high"
        assert LibraryHealthSeverity.MEDIUM == "medium"
        assert LibraryHealthSeverity.LOW == "low"


class TestLibraryHealthFinding:
    def _make(self, **kwargs) -> LibraryHealthFinding:  # type: ignore[no-untyped-def]
        defaults: dict = {
            "alias": "my-lib",
            "coordinate": "com.example:my-lib",
            "version": "1.0.0",
            "signal": HealthSignal.CURATED,
            "severity": LibraryHealthSeverity.HIGH,
            "message": "Deprecated.",
        }
        defaults.update(kwargs)
        return LibraryHealthFinding(**defaults)  # type: ignore[arg-type]

    def test_minimal_fields(self) -> None:
        f = self._make()
        assert f.alias == "my-lib"
        assert f.coordinate == "com.example:my-lib"
        assert f.version == "1.0.0"
        assert f.signal == HealthSignal.CURATED
        assert f.severity == LibraryHealthSeverity.HIGH
        assert f.message == "Deprecated."

    def test_optional_fields_default_to_none(self) -> None:
        f = self._make()
        assert f.replacement is None
        assert f.migration_url is None
        assert f.days_since_release is None

    def test_optional_fields_set(self) -> None:
        f = self._make(
            replacement="com.example:new-lib",
            migration_url="https://example.com/migrate",
            days_since_release=800,
        )
        assert f.replacement == "com.example:new-lib"
        assert f.migration_url == "https://example.com/migrate"
        assert f.days_since_release == 800

    def test_frozen_dataclass(self) -> None:
        f = self._make()
        with pytest.raises(AttributeError):
            f.alias = "other"  # type: ignore[misc]

    def test_inactive_finding(self) -> None:
        f = self._make(signal=HealthSignal.INACTIVE, severity=LibraryHealthSeverity.MEDIUM)
        assert f.signal == HealthSignal.INACTIVE
        assert f.severity == LibraryHealthSeverity.MEDIUM

    def test_relocated_finding(self) -> None:
        f = self._make(
            signal=HealthSignal.RELOCATED,
            replacement="com.new:artifact",
        )
        assert f.signal == HealthSignal.RELOCATED
        assert f.replacement == "com.new:artifact"
