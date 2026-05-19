"""Integration tests for the 'diff' CLI command."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from gradle_deps_monitor.cli import app

runner = CliRunner()

# ---------------------------------------------------------------------------
# Minimal valid freeze.json fixtures
# ---------------------------------------------------------------------------

_FREEZE_AFTER: dict = {
    "schema_version": "1",
    "generated_at": "2026-05-04T10:00:00+00:00",
    "catalog": {
        "source_path": "gradle/libs.versions.toml",
        "library_count": 2,
        "plugin_count": 1,
        "bundle_count": 0,
        "libraries": [
            {
                "alias": "core-ktx",
                "group": "androidx.core",
                "artifact": "core-ktx",
                "version": "1.14.0",
                "stability": "stable",
            },
            {
                "alias": "retrofit",
                "group": "com.squareup.retrofit2",
                "artifact": "retrofit",
                "version": "2.10.0",
                "stability": "stable",
            },
        ],
        "plugins": [
            {
                "alias": "kotlin-android",
                "id": "org.jetbrains.kotlin.android",
                "version": "2.0.0",
                "stability": "stable",
            }
        ],
        "bundles": [],
    },
    "health": {
        "finding_count": 0,
        "findings": [],
    },
}

_FREEZE_BEFORE: dict = {
    "schema_version": "1",
    "generated_at": "2026-04-18T10:00:00+00:00",
    "catalog": {
        "source_path": "gradle/libs.versions.toml",
        "library_count": 1,
        "plugin_count": 1,
        "bundle_count": 0,
        "libraries": [
            {
                "alias": "core-ktx",
                "group": "androidx.core",
                "artifact": "core-ktx",
                "version": "1.13.0",
                "stability": "stable",
            },
        ],
        "plugins": [
            {
                "alias": "kotlin-android",
                "id": "org.jetbrains.kotlin.android",
                "version": "1.9.0",
                "stability": "stable",
            }
        ],
        "bundles": [],
    },
    "health": {
        "finding_count": 0,
        "findings": [],
    },
}


def _write_freeze(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


# ===========================================================================
# Exit codes
# ===========================================================================


def test_diff_exits_zero_baseline(tmp_path: Path) -> None:
    after = tmp_path / "freeze.json"
    _write_freeze(after, _FREEZE_AFTER)
    out = tmp_path / "reports"

    result = runner.invoke(app, ["diff", str(after), "--out", str(out)])

    assert result.exit_code == 0


def test_diff_exits_zero_with_prev(tmp_path: Path) -> None:
    after = tmp_path / "after.json"
    before = tmp_path / "before.json"
    _write_freeze(after, _FREEZE_AFTER)
    _write_freeze(before, _FREEZE_BEFORE)
    out = tmp_path / "reports"

    result = runner.invoke(app, ["diff", str(after), "--prev", str(before), "--out", str(out)])

    assert result.exit_code == 0


def test_diff_exits_nonzero_when_after_missing(tmp_path: Path) -> None:
    result = runner.invoke(app, ["diff", str(tmp_path / "nonexistent.json")])
    assert result.exit_code != 0


def test_diff_exits_nonzero_when_prev_missing(tmp_path: Path) -> None:
    after = tmp_path / "after.json"
    _write_freeze(after, _FREEZE_AFTER)

    result = runner.invoke(
        app,
        ["diff", str(after), "--prev", str(tmp_path / "nonexistent.json")],
    )

    assert result.exit_code != 0


# ===========================================================================
# Output files
# ===========================================================================


def test_diff_creates_markdown_file(tmp_path: Path) -> None:
    after = tmp_path / "freeze.json"
    _write_freeze(after, _FREEZE_AFTER)
    out = tmp_path / "reports"

    runner.invoke(app, ["diff", str(after), "--out", str(out)])

    assert (out / "freeze-diff.md").exists()


def test_diff_creates_json_file(tmp_path: Path) -> None:
    after = tmp_path / "freeze.json"
    _write_freeze(after, _FREEZE_AFTER)
    out = tmp_path / "reports"

    runner.invoke(app, ["diff", str(after), "--out", str(out)])

    assert (out / "freeze-diff.json").exists()


def test_diff_creates_slack_json_file_when_flag_passed(tmp_path: Path) -> None:
    after = tmp_path / "freeze.json"
    _write_freeze(after, _FREEZE_AFTER)
    out = tmp_path / "reports"

    runner.invoke(app, ["diff", str(after), "--out", str(out), "--slack"])

    # RFC-0034: Slack writer is opt-in; only emitted when --slack is passed.
    assert (out / "freeze-diff-slack.json").exists()


def test_diff_default_omits_slack(tmp_path: Path) -> None:
    after = tmp_path / "freeze.json"
    _write_freeze(after, _FREEZE_AFTER)
    out = tmp_path / "reports"

    runner.invoke(app, ["diff", str(after), "--out", str(out)])

    # RFC-0034: Slack writer is opt-in; default omits it.
    assert not (out / "freeze-diff-slack.json").exists()


def test_diff_json_is_valid_json(tmp_path: Path) -> None:
    after = tmp_path / "freeze.json"
    _write_freeze(after, _FREEZE_AFTER)
    out = tmp_path / "reports"

    runner.invoke(app, ["diff", str(after), "--out", str(out)])

    data = json.loads((out / "freeze-diff.json").read_text(encoding="utf-8"))
    assert data["schema_version"] == "1.1.0"


def test_diff_slack_json_has_blocks(tmp_path: Path) -> None:
    after = tmp_path / "freeze.json"
    _write_freeze(after, _FREEZE_AFTER)
    out = tmp_path / "reports"

    runner.invoke(app, ["diff", str(after), "--out", str(out), "--slack"])

    data = json.loads((out / "freeze-diff-slack.json").read_text(encoding="utf-8"))
    assert "blocks" in data


# ===========================================================================
# Baseline mode
# ===========================================================================


def test_diff_baseline_sets_is_baseline_true(tmp_path: Path) -> None:
    after = tmp_path / "freeze.json"
    _write_freeze(after, _FREEZE_AFTER)
    out = tmp_path / "reports"

    runner.invoke(app, ["diff", str(after), "--out", str(out)])

    data = json.loads((out / "freeze-diff.json").read_text(encoding="utf-8"))
    assert data["is_baseline"] is True


def test_diff_regular_sets_is_baseline_false(tmp_path: Path) -> None:
    after = tmp_path / "after.json"
    before = tmp_path / "before.json"
    _write_freeze(after, _FREEZE_AFTER)
    _write_freeze(before, _FREEZE_BEFORE)
    out = tmp_path / "reports"

    runner.invoke(app, ["diff", str(after), "--prev", str(before), "--out", str(out)])

    data = json.loads((out / "freeze-diff.json").read_text(encoding="utf-8"))
    assert data["is_baseline"] is False


def test_diff_markdown_contains_baseline_text(tmp_path: Path) -> None:
    after = tmp_path / "freeze.json"
    _write_freeze(after, _FREEZE_AFTER)
    out = tmp_path / "reports"

    runner.invoke(app, ["diff", str(after), "--out", str(out)])

    content = (out / "freeze-diff.md").read_text(encoding="utf-8")
    assert "Baseline" in content


# ===========================================================================
# Console output
# ===========================================================================


def test_diff_prints_output_path(tmp_path: Path) -> None:
    after = tmp_path / "freeze.json"
    _write_freeze(after, _FREEZE_AFTER)
    out = tmp_path / "reports"

    result = runner.invoke(app, ["diff", str(after), "--out", str(out)])

    assert "Reports written" in result.output


def test_diff_default_output_dir_is_reports(tmp_path: Path) -> None:
    after = tmp_path / "freeze.json"
    _write_freeze(after, _FREEZE_AFTER)

    runner.invoke(app, ["diff", str(after)], catch_exceptions=False)

    assert Path("reports/freeze-diff.json").exists()


def test_diff_with_prev_shows_diff_output(tmp_path: Path) -> None:
    after = tmp_path / "after.json"
    before = tmp_path / "before.json"
    _write_freeze(after, _FREEZE_AFTER)
    _write_freeze(before, _FREEZE_BEFORE)
    out = tmp_path / "reports"

    result = runner.invoke(app, ["diff", str(after), "--prev", str(before), "--out", str(out)])

    # Rich output contains diff information
    assert result.exit_code == 0
    assert "Reports written" in result.output


def test_diff_detects_library_upgrade(tmp_path: Path) -> None:
    after = tmp_path / "after.json"
    before = tmp_path / "before.json"
    _write_freeze(after, _FREEZE_AFTER)
    _write_freeze(before, _FREEZE_BEFORE)
    out = tmp_path / "reports"

    runner.invoke(app, ["diff", str(after), "--prev", str(before), "--out", str(out)])

    data = json.loads((out / "freeze-diff.json").read_text(encoding="utf-8"))
    # core-ktx went from 1.13.0 → 1.14.0 (minor bump)
    assert data["summary"]["libraries"]["minor"] == 1
    # retrofit was added
    assert data["summary"]["libraries"]["added"] == 1
