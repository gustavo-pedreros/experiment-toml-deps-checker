"""Unit tests for the compliance domain model."""

from __future__ import annotations

import dataclasses

import pytest

from gradle_deps_monitor.domain.compliance import ComplianceFinding, ComplianceSeverity


class TestComplianceFinding:
    def test_fields_stored(self) -> None:
        f = ComplianceFinding(
            rule_id="PLAY-DEP-001",
            severity=ComplianceSeverity.ERROR,
            message="SafetyNet is deprecated",
            detail="Migrate to Play Integrity API.",
            deadline="2025-01-31",
            migration="com.google.android.play:integrity",
        )
        assert f.rule_id == "PLAY-DEP-001"
        assert f.severity == ComplianceSeverity.ERROR
        assert f.message == "SafetyNet is deprecated"
        assert f.detail == "Migrate to Play Integrity API."
        assert f.deadline == "2025-01-31"
        assert f.migration == "com.google.android.play:integrity"

    def test_optional_fields_default_to_none(self) -> None:
        f = ComplianceFinding(
            rule_id="PLAY-X",
            severity=ComplianceSeverity.INFO,
            message="All good",
        )
        assert f.detail == ""
        assert f.deadline is None
        assert f.migration is None

    def test_immutable(self) -> None:
        f = ComplianceFinding(
            rule_id="PLAY-X",
            severity=ComplianceSeverity.WARNING,
            message="Upcoming deadline",
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            f.severity = ComplianceSeverity.ERROR  # type: ignore[misc]

    def test_severity_values(self) -> None:
        assert ComplianceSeverity.ERROR == "error"
        assert ComplianceSeverity.WARNING == "warning"
        assert ComplianceSeverity.INFO == "info"
