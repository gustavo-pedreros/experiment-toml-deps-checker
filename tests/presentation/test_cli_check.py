"""Integration tests for the 'check' CLI command."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from gradle_deps_monitor.cli import app

runner = CliRunner()

# ---------------------------------------------------------------------------
# Minimal valid catalog fixtures
# ---------------------------------------------------------------------------

_ONE_LIBRARY_TOML = """\
[libraries]
core-ktx = { module = "androidx.core:core-ktx", version = "1.13.0" }
"""

_FULL_CATALOG_TOML = """\
[versions]
kotlin = "2.0.0"

[libraries]
core-ktx = { module = "androidx.core:core-ktx", version = "1.13.0" }
kotlin-stdlib = { module = "org.jetbrains.kotlin:kotlin-stdlib", version.ref = "kotlin" }

[plugins]
kotlin-android = { id = "org.jetbrains.kotlin.android", version.ref = "kotlin" }

[bundles]
androidx = ["core-ktx"]
"""

_MALFORMED_TOML = "[[[ this is not valid TOML"


def _make_gradle_dir(tmp_path: Path, content: str) -> Path:
    gradle_dir = tmp_path / "gradle"
    gradle_dir.mkdir()
    (gradle_dir / "libs.versions.toml").write_text(content, encoding="utf-8")
    return gradle_dir


# ---------------------------------------------------------------------------
# Exit codes
# ---------------------------------------------------------------------------


def test_check_exits_zero_for_valid_catalog(tmp_path: Path) -> None:
    gradle_dir = _make_gradle_dir(tmp_path, _ONE_LIBRARY_TOML)
    out = tmp_path / "reports"
    result = runner.invoke(app, ["check", str(gradle_dir), "--out", str(out)])
    assert result.exit_code == 0


def test_check_exits_nonzero_for_missing_toml(tmp_path: Path) -> None:
    gradle_dir = tmp_path / "gradle"
    gradle_dir.mkdir()  # no libs.versions.toml inside
    out = tmp_path / "reports"
    result = runner.invoke(app, ["check", str(gradle_dir), "--out", str(out)])
    assert result.exit_code == 1


def test_check_exits_nonzero_for_malformed_toml(tmp_path: Path) -> None:
    gradle_dir = _make_gradle_dir(tmp_path, _MALFORMED_TOML)
    out = tmp_path / "reports"
    result = runner.invoke(app, ["check", str(gradle_dir), "--out", str(out)])
    assert result.exit_code == 1


# ---------------------------------------------------------------------------
# Output files
# ---------------------------------------------------------------------------


def test_check_creates_markdown_report(tmp_path: Path) -> None:
    gradle_dir = _make_gradle_dir(tmp_path, _ONE_LIBRARY_TOML)
    out = tmp_path / "reports"
    runner.invoke(app, ["check", str(gradle_dir), "--out", str(out)])
    assert (out / "freeze.md").exists()


def test_check_creates_json_report(tmp_path: Path) -> None:
    gradle_dir = _make_gradle_dir(tmp_path, _ONE_LIBRARY_TOML)
    out = tmp_path / "reports"
    runner.invoke(app, ["check", str(gradle_dir), "--out", str(out)])
    assert (out / "freeze.json").exists()


def test_check_json_report_is_valid(tmp_path: Path) -> None:
    gradle_dir = _make_gradle_dir(tmp_path, _ONE_LIBRARY_TOML)
    out = tmp_path / "reports"
    runner.invoke(app, ["check", str(gradle_dir), "--out", str(out)])
    data = json.loads((out / "freeze.json").read_text(encoding="utf-8"))
    assert data["schema_version"] == "1.0.0"
    assert data["catalog"]["library_count"] == 1


# ---------------------------------------------------------------------------
# Console output
# ---------------------------------------------------------------------------


def test_check_prints_output_path(tmp_path: Path) -> None:
    gradle_dir = _make_gradle_dir(tmp_path, _ONE_LIBRARY_TOML)
    out = tmp_path / "reports"
    result = runner.invoke(app, ["check", str(gradle_dir), "--out", str(out)])
    assert "Reports written" in result.stdout


def test_check_prints_library_count(tmp_path: Path) -> None:
    gradle_dir = _make_gradle_dir(tmp_path, _FULL_CATALOG_TOML)
    out = tmp_path / "reports"
    result = runner.invoke(app, ["check", str(gradle_dir), "--out", str(out)])
    assert "Libraries" in result.stdout
    assert "2" in result.stdout


def test_check_prints_plugin_count(tmp_path: Path) -> None:
    gradle_dir = _make_gradle_dir(tmp_path, _FULL_CATALOG_TOML)
    out = tmp_path / "reports"
    result = runner.invoke(app, ["check", str(gradle_dir), "--out", str(out)])
    assert "Plugins" in result.stdout
    assert "1" in result.stdout


def test_check_prints_error_message_on_failure(tmp_path: Path) -> None:
    gradle_dir = _make_gradle_dir(tmp_path, _MALFORMED_TOML)
    out = tmp_path / "reports"
    result = runner.invoke(app, ["check", str(gradle_dir), "--out", str(out)])
    assert "Error:" in result.output


# ---------------------------------------------------------------------------
# Custom output directory
# ---------------------------------------------------------------------------


def test_check_respects_custom_output_dir(tmp_path: Path) -> None:
    gradle_dir = _make_gradle_dir(tmp_path, _ONE_LIBRARY_TOML)
    custom_out = tmp_path / "custom" / "nested" / "output"
    runner.invoke(app, ["check", str(gradle_dir), "--out", str(custom_out)])
    assert (custom_out / "freeze.md").exists()
    assert (custom_out / "freeze.json").exists()


def test_check_short_flag_o_works(tmp_path: Path) -> None:
    gradle_dir = _make_gradle_dir(tmp_path, _ONE_LIBRARY_TOML)
    out = tmp_path / "reports"
    result = runner.invoke(app, ["check", str(gradle_dir), "-o", str(out)])
    assert result.exit_code == 0
    assert (out / "freeze.md").exists()
