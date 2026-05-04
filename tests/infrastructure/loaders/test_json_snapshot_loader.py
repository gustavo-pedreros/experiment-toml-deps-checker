"""Unit tests for JsonSnapshotLoader."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from gradle_deps_monitor.infrastructure.loaders.json_snapshot_loader import JsonSnapshotLoader

_LOADER = JsonSnapshotLoader()

# ---------------------------------------------------------------------------
# Minimal valid freeze.json fixture
# ---------------------------------------------------------------------------

_MINIMAL_JSON: dict = {
    "schema_version": "1",
    "generated_at": "2026-05-04T10:00:00+00:00",
    "catalog": {
        "source_path": "gradle/libs.versions.toml",
        "library_count": 1,
        "plugin_count": 0,
        "bundle_count": 0,
        "libraries": [
            {
                "alias": "core-ktx",
                "group": "androidx.core",
                "artifact": "core-ktx",
                "version": "1.13.0",
                "stability": "stable",
            }
        ],
        "plugins": [],
        "bundles": [],
    },
    "health": {
        "finding_count": 0,
        "findings": [],
    },
}

_FULL_JSON: dict = {
    "schema_version": "1",
    "generated_at": "2026-04-18T08:00:00+00:00",
    "catalog": {
        "source_path": "gradle/libs.versions.toml",
        "library_count": 2,
        "plugin_count": 1,
        "bundle_count": 1,
        "libraries": [
            {
                "alias": "core-ktx",
                "group": "androidx.core",
                "artifact": "core-ktx",
                "version": "1.12.0",
                "stability": "stable",
            },
            {
                "alias": "appcompat",
                "group": "androidx.appcompat",
                "artifact": "appcompat",
                "version": "1.7.0-alpha01",
                "stability": "alpha",
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
        "bundles": [{"alias": "androidx", "members": ["core-ktx", "appcompat"]}],
    },
    "health": {
        "finding_count": 1,
        "findings": [
            {
                "rule_id": "HDX-004",
                "severity": "warning",
                "message": "no [plugins] block in a non-empty catalog",
            }
        ],
    },
}


def _write(tmp_path: Path, data: dict, filename: str = "freeze.json") -> Path:
    p = tmp_path / filename
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_load_returns_snapshot(tmp_path: Path) -> None:
    p = _write(tmp_path, _MINIMAL_JSON)
    snap = _LOADER.load(p)
    assert snap.schema_version == "1"


def test_load_parses_generated_at(tmp_path: Path) -> None:
    p = _write(tmp_path, _MINIMAL_JSON)
    snap = _LOADER.load(p)
    assert snap.generated_at.year == 2026
    assert snap.generated_at.month == 5
    assert snap.generated_at.day == 4


def test_load_parses_source_path(tmp_path: Path) -> None:
    p = _write(tmp_path, _MINIMAL_JSON)
    snap = _LOADER.load(p)
    assert snap.source_path == "gradle/libs.versions.toml"


def test_load_parses_libraries(tmp_path: Path) -> None:
    p = _write(tmp_path, _MINIMAL_JSON)
    snap = _LOADER.load(p)
    assert len(snap.libraries) == 1
    lib = snap.libraries[0]
    assert lib.alias == "core-ktx"
    assert lib.coordinate == "androidx.core:core-ktx"
    assert lib.version == "1.13.0"


def test_load_parses_plugins(tmp_path: Path) -> None:
    p = _write(tmp_path, _FULL_JSON)
    snap = _LOADER.load(p)
    assert len(snap.plugins) == 1
    plugin = snap.plugins[0]
    assert plugin.alias == "kotlin-android"
    assert plugin.plugin_id == "org.jetbrains.kotlin.android"
    assert plugin.version == "1.9.0"


def test_load_parses_findings(tmp_path: Path) -> None:
    p = _write(tmp_path, _FULL_JSON)
    snap = _LOADER.load(p)
    assert len(snap.findings) == 1
    finding = snap.findings[0]
    assert finding.rule_id == "HDX-004"
    assert finding.severity == "warning"


def test_load_empty_sections(tmp_path: Path) -> None:
    p = _write(tmp_path, _MINIMAL_JSON)
    snap = _LOADER.load(p)
    assert snap.plugins == ()
    assert snap.findings == ()


def test_load_multiple_libraries(tmp_path: Path) -> None:
    p = _write(tmp_path, _FULL_JSON)
    snap = _LOADER.load(p)
    assert len(snap.libraries) == 2


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


def test_load_raises_file_not_found(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="Freeze report not found"):
        _LOADER.load(tmp_path / "nonexistent.json")


def test_load_raises_on_invalid_json(tmp_path: Path) -> None:
    p = tmp_path / "bad.json"
    p.write_text("{ this is not json", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid JSON"):
        _LOADER.load(p)


def test_load_raises_on_unsupported_schema(tmp_path: Path) -> None:
    data = {**_MINIMAL_JSON, "schema_version": "99"}
    p = _write(tmp_path, data)
    with pytest.raises(ValueError, match="Unsupported schema_version"):
        _LOADER.load(p)


def test_load_raises_on_missing_generated_at(tmp_path: Path) -> None:
    data = {k: v for k, v in _MINIMAL_JSON.items() if k != "generated_at"}
    p = _write(tmp_path, data)
    with pytest.raises(ValueError, match="generated_at"):
        _LOADER.load(p)


def test_load_raises_on_malformed_generated_at(tmp_path: Path) -> None:
    data = {**_MINIMAL_JSON, "generated_at": "not-a-date"}
    p = _write(tmp_path, data)
    with pytest.raises(ValueError, match="generated_at"):
        _LOADER.load(p)


def test_load_raises_on_library_missing_key(tmp_path: Path) -> None:
    data = {
        **_MINIMAL_JSON,
        "catalog": {
            **_MINIMAL_JSON["catalog"],
            "libraries": [{"alias": "core-ktx"}],  # missing group/artifact/version
        },
    }
    p = _write(tmp_path, data)
    with pytest.raises(ValueError, match="Library entry missing key"):
        _LOADER.load(p)
