"""Tests for Finding and Severity domain objects."""

from __future__ import annotations

import pytest

from gradle_deps_monitor.domain.finding import Finding, Severity


def test_severity_values() -> None:
    assert Severity.ERROR == "error"
    assert Severity.WARNING == "warning"
    assert Severity.INFO == "info"
    assert Severity.SUGGESTION == "suggestion"


def test_finding_is_frozen() -> None:
    f = Finding(rule_id="catalog.test", severity=Severity.INFO, message="msg")
    with pytest.raises(AttributeError):
        f.message = "changed"  # type: ignore[misc]


def test_finding_details_defaults_to_empty_string() -> None:
    f = Finding(rule_id="catalog.test", severity=Severity.WARNING, message="msg")
    assert f.details == ""


def test_finding_equality() -> None:
    f1 = Finding(rule_id="catalog.test", severity=Severity.ERROR, message="m", details="d")
    f2 = Finding(rule_id="catalog.test", severity=Severity.ERROR, message="m", details="d")
    assert f1 == f2


def test_finding_inequality_on_severity() -> None:
    f1 = Finding(rule_id="catalog.test", severity=Severity.ERROR, message="m")
    f2 = Finding(rule_id="catalog.test", severity=Severity.WARNING, message="m")
    assert f1 != f2
