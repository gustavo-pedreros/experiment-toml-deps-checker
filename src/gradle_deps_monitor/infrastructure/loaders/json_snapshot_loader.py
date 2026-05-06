"""JsonSnapshotLoader — loads a freeze.json file into a FreezeSnapshot."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from gradle_deps_monitor.application.ports.snapshot_loader import (
    FindingSnapshot,
    FreezeSnapshot,
    LibrarySnapshot,
    PluginSnapshot,
)

# Compatibility window for ``schema_version``.
#
# Per ADR-0008, the JSON schema follows SemVer. The loader accepts any MINOR
# bump within ``_SUPPORTED_MAJOR`` and tolerates unknown additive fields. The
# legacy literal ``"1"`` is also accepted to keep older committed reports
# loadable.
_SUPPORTED_MAJOR = "1"
_LEGACY_VERSIONS = {"1"}


class JsonSnapshotLoader:
    """Loads a previously written ``freeze.json`` as a :class:`FreezeSnapshot`.

    Raises
    ------
    FileNotFoundError
        If *path* does not exist.
    ValueError
        If the file is not valid JSON, is missing required keys, or has an
        unsupported ``schema_version``.
    """

    def load(self, path: Path) -> FreezeSnapshot:
        """Read *path* and return a :class:`FreezeSnapshot`."""
        if not path.exists():
            raise FileNotFoundError(f"Freeze report not found: {path}")

        try:
            data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in {path}: {exc}") from exc

        return _parse(data, path)


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def _is_supported_schema(schema: object) -> bool:
    if not isinstance(schema, str) or not schema:
        return False
    if schema in _LEGACY_VERSIONS:
        return True
    head = schema.split(".", 1)[0]
    return head == _SUPPORTED_MAJOR


def _parse(data: dict[str, Any], path: Path) -> FreezeSnapshot:
    schema = data.get("schema_version", "")
    if not _is_supported_schema(schema):
        raise ValueError(
            f"Unsupported schema_version {schema!r} in {path}. "
            f"Supported: {_SUPPORTED_MAJOR}.x.y (or legacy {sorted(_LEGACY_VERSIONS)})"
        )

    try:
        generated_at = datetime.fromisoformat(data["generated_at"])
    except (KeyError, ValueError) as exc:
        raise ValueError(f"Invalid or missing 'generated_at' in {path}") from exc

    catalog = data.get("catalog", {})
    source_path = catalog.get("source_path", "")

    libraries = tuple(_parse_library(lib) for lib in catalog.get("libraries", []))
    plugins = tuple(_parse_plugin(p) for p in catalog.get("plugins", []))

    health = data.get("health", {})
    findings = tuple(_parse_finding(f) for f in health.get("findings", []))

    return FreezeSnapshot(
        schema_version=schema,
        generated_at=generated_at,
        source_path=source_path,
        libraries=libraries,
        plugins=plugins,
        findings=findings,
    )


def _parse_library(obj: dict[str, Any]) -> LibrarySnapshot:
    try:
        return LibrarySnapshot(
            alias=obj["alias"],
            coordinate=f"{obj['group']}:{obj['artifact']}",
            version=obj["version"],
        )
    except KeyError as exc:
        raise ValueError(f"Library entry missing key {exc}: {obj}") from exc


def _parse_plugin(obj: dict[str, Any]) -> PluginSnapshot:
    try:
        return PluginSnapshot(
            alias=obj["alias"],
            plugin_id=obj["id"],
            version=obj["version"],
        )
    except KeyError as exc:
        raise ValueError(f"Plugin entry missing key {exc}: {obj}") from exc


def _parse_finding(obj: dict[str, Any]) -> FindingSnapshot:
    try:
        return FindingSnapshot(
            rule_id=obj["rule_id"],
            severity=obj["severity"],
            message=obj["message"],
        )
    except KeyError as exc:
        raise ValueError(f"Finding entry missing key {exc}: {obj}") from exc
