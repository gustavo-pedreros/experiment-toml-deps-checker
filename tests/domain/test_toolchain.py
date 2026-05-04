"""Tests for domain/toolchain.py."""

from __future__ import annotations

import pytest

from gradle_deps_monitor.domain.toolchain import ToolchainFinding, ToolchainSeverity


class TestToolchainSeverity:
    def test_values(self) -> None:
        assert ToolchainSeverity.ERROR == "error"
        assert ToolchainSeverity.WARNING == "warning"
        assert ToolchainSeverity.INFO == "info"


class TestToolchainFinding:
    def test_required_fields(self) -> None:
        f = ToolchainFinding(
            rule_id="TOOL-KC-001",
            severity=ToolchainSeverity.ERROR,
            message="some message",
        )
        assert f.rule_id == "TOOL-KC-001"
        assert f.severity == ToolchainSeverity.ERROR
        assert f.message == "some message"
        assert f.detail == ""
        assert f.recommendation == ""

    def test_optional_fields(self) -> None:
        f = ToolchainFinding(
            rule_id="TOOL-KSP-001",
            severity=ToolchainSeverity.WARNING,
            message="msg",
            detail="extra detail",
            recommendation="do this",
        )
        assert f.detail == "extra detail"
        assert f.recommendation == "do this"

    def test_immutable(self) -> None:
        f = ToolchainFinding(
            rule_id="TOOL-AGP-001",
            severity=ToolchainSeverity.ERROR,
            message="msg",
        )
        with pytest.raises(AttributeError):
            f.rule_id = "OTHER"  # type: ignore[misc]

    def test_equality(self) -> None:
        f1 = ToolchainFinding(rule_id="X", severity=ToolchainSeverity.INFO, message="m")
        f2 = ToolchainFinding(rule_id="X", severity=ToolchainSeverity.INFO, message="m")
        assert f1 == f2
