"""Tests for the domain-layer Policy value objects (RFC-0018 v1)."""

from __future__ import annotations

from gradle_deps_monitor.domain.policy import (
    Policy,
    PolicyResult,
    PolicyViolation,
    WarningCategory,
)
from gradle_deps_monitor.domain.severity import CommonSeverity


class TestWarningCategory:
    def test_seven_documented_categories_exist(self) -> None:
        """RFC-0018 documents seven warning categories — keep them in lockstep."""
        assert {c.value for c in WarningCategory} == {
            "high-vulnerability",
            "compliance",
            "toolchain",
            "library-health",
            "deprecated",
            "breaking",
            "license",
        }


class TestPolicy:
    def test_default_is_a_noop(self) -> None:
        p = Policy()
        assert p.fail_on_errors is False
        assert p.warn_on == frozenset()

    def test_warn_on_accepts_frozenset(self) -> None:
        p = Policy(warn_on=frozenset({WarningCategory.BREAKING}))
        assert WarningCategory.BREAKING in p.warn_on

    def test_is_hashable_when_default(self) -> None:
        """Frozen dataclass with default frozenset stays usable in sets/dicts."""
        a = Policy()
        b = Policy()
        assert a == b


class TestPolicyResult:
    def test_empty_result_does_not_fail(self) -> None:
        assert PolicyResult().should_fail is False

    def test_any_violation_triggers_should_fail(self) -> None:
        v = PolicyViolation(
            category="security",
            severity=CommonSeverity.ERROR,
            message="boom",
            target="lib",
        )
        assert PolicyResult(violations=(v,)).should_fail is True

    def test_warnings_alone_do_not_trigger_should_fail(self) -> None:
        w = PolicyViolation(
            category="breaking",
            severity=CommonSeverity.WARNING,
            message="watch out",
            target="lib",
        )
        assert PolicyResult(warnings=(w,)).should_fail is False
