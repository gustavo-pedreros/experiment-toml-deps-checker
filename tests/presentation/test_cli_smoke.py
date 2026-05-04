"""Smoke tests for the Typer CLI.

These tests verify the CLI wiring is in place. They do not exercise the
business logic of any specific command.
"""

from pathlib import Path

from typer.testing import CliRunner

from gradle_deps_monitor import __version__
from gradle_deps_monitor.cli import app

runner = CliRunner()


def test_version_flag_prints_version() -> None:
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_help_lists_check_command() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "check" in result.stdout


def test_check_command_accepts_existing_directory(tmp_path: Path) -> None:
    catalog_dir = tmp_path / "gradle"
    catalog_dir.mkdir()

    result = runner.invoke(app, ["check", str(catalog_dir)])

    assert result.exit_code == 0
    assert "not yet implemented" in result.stdout


def test_check_command_rejects_missing_directory(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist"

    result = runner.invoke(app, ["check", str(missing)])

    assert result.exit_code != 0
