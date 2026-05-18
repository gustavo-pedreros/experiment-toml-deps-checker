"""Tests for the policy presentation helpers (RFC-0018 v1)."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from rich.console import Console

from gradle_deps_monitor.domain.policy import PolicyResult, PolicyViolation
from gradle_deps_monitor.domain.severity import CommonSeverity
from gradle_deps_monitor.presentation.policy_output import (
    emit_github_actions_annotations,
    print_policy_section,
)

_ERR = PolicyViolation(
    category="security",
    severity=CommonSeverity.ERROR,
    message="Critical CVE GHSA-aaaa-bbbb-cccc: example",
    target="lib-a",
)
_WARN = PolicyViolation(
    category="breaking",
    severity=CommonSeverity.WARNING,
    message="Likely-breaking upgrade 1.0 → 2.0",
    target="lib-b",
)


def _render(result: PolicyResult) -> str:
    buf = io.StringIO()
    console = Console(file=buf, force_terminal=False, width=120, no_color=True)
    print_policy_section(result, console=console)
    return buf.getvalue()


class TestPrintPolicySection:
    def test_empty_result_prints_nothing(self) -> None:
        assert _render(PolicyResult()) == ""

    def test_violations_render_with_title(self) -> None:
        out = _render(PolicyResult(violations=(_ERR,)))
        assert "Policy violations" in out
        assert "lib-a" in out
        assert "GHSA-aaaa-bbbb-cccc" in out

    def test_warnings_render_with_title(self) -> None:
        out = _render(PolicyResult(warnings=(_WARN,)))
        assert "Policy warnings" in out
        assert "lib-b" in out

    def test_both_panels_render_in_one_call(self) -> None:
        out = _render(PolicyResult(violations=(_ERR,), warnings=(_WARN,)))
        assert "Policy violations" in out
        assert "Policy warnings" in out


class TestEmitGitHubActionsAnnotations:
    def test_noop_when_env_is_not_set(self, capsys: pytest.CaptureFixture[str]) -> None:
        emit_github_actions_annotations(
            PolicyResult(violations=(_ERR,)),
            Path("/tmp/gradle"),
            env={},
        )
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == ""

    def test_noop_when_env_is_not_true(self, capsys: pytest.CaptureFixture[str]) -> None:
        emit_github_actions_annotations(
            PolicyResult(violations=(_ERR,)),
            Path("/tmp/gradle"),
            env={"GITHUB_ACTIONS": "false"},
        )
        assert capsys.readouterr().out == ""

    def test_error_annotation_when_active(
        self, capsys: pytest.CaptureFixture[str], tmp_path: Path
    ) -> None:
        emit_github_actions_annotations(
            PolicyResult(violations=(_ERR,)),
            tmp_path,
            env={"GITHUB_ACTIONS": "true"},
        )
        out = capsys.readouterr().out
        assert out.startswith("::error file=")
        assert "[security]" in out
        assert "lib-a" in out

    def test_warning_annotation_when_active(
        self, capsys: pytest.CaptureFixture[str], tmp_path: Path
    ) -> None:
        emit_github_actions_annotations(
            PolicyResult(warnings=(_WARN,)),
            tmp_path,
            env={"GITHUB_ACTIONS": "true"},
        )
        out = capsys.readouterr().out
        assert out.startswith("::warning file=")
        assert "[breaking]" in out

    def test_one_annotation_per_finding(
        self, capsys: pytest.CaptureFixture[str], tmp_path: Path
    ) -> None:
        emit_github_actions_annotations(
            PolicyResult(violations=(_ERR, _ERR), warnings=(_WARN,)),
            tmp_path,
            env={"GITHUB_ACTIONS": "true"},
        )
        lines = [line for line in capsys.readouterr().out.splitlines() if line]
        assert len(lines) == 3

    def test_message_special_chars_are_escaped(
        self, capsys: pytest.CaptureFixture[str], tmp_path: Path
    ) -> None:
        nasty = PolicyViolation(
            category="security",
            severity=CommonSeverity.ERROR,
            message="Boom\nwith :: colons and 100%",
            target="lib",
        )
        emit_github_actions_annotations(
            PolicyResult(violations=(nasty,)),
            tmp_path,
            env={"GITHUB_ACTIONS": "true"},
        )
        out = capsys.readouterr().out
        # newline → %0A, colon → %3A, percent → %25
        assert "%0A" in out
        assert "%3A" in out
        assert "%25" in out
        assert "\n" not in out.rstrip("\n")  # only the trailing print() newline
