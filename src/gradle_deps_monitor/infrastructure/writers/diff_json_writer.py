"""DiffJsonWriter — serialises a FreezeDiff to schema-versioned JSON."""

from __future__ import annotations

import contextlib
import json
from pathlib import Path
from typing import Any

from gradle_deps_monitor.domain.diff import (
    FindingChange,
    FreezeDiff,
    LibraryChange,
    PluginChange,
    VersionBump,
)
from gradle_deps_monitor.domain.finding import Severity
from gradle_deps_monitor.infrastructure.writers._atomic import atomic_write

# Schema version for the freeze-diff.json output. Follows SemVer per ADR-0008,
# bumped independently from the freeze.json schema version.
# 1.0.0 → 1.1.0: additive ``common_severity`` field on finding_change entries
# (RFC-0016b).
SCHEMA_VERSION = "1.1.0"


class DiffJsonWriter:
    """Writes a :class:`~gradle_deps_monitor.domain.diff.FreezeDiff` as pretty-printed JSON.

    Schema version: see :data:`SCHEMA_VERSION` (currently ``"1.0.0"``).
    """

    def write(self, diff: FreezeDiff, dest: Path) -> None:
        """Write *diff* to *dest*, creating parent directories as needed."""
        with atomic_write(dest) as fh:
            fh.write(json.dumps(_serialise(diff), indent=2, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------


def _serialise(diff: FreezeDiff) -> dict[str, Any]:
    before_ts = (
        diff.before_generated_at.isoformat(timespec="seconds") if diff.before_generated_at else None
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "before_generated_at": before_ts,
        "after_generated_at": diff.after_generated_at.isoformat(timespec="seconds"),
        "is_baseline": diff.is_baseline,
        "summary": _summary(diff),
        "libraries": {
            "added": [_lib_change(c) for c in diff.libraries_added],
            "removed": [_lib_change(c) for c in diff.libraries_removed],
            "upgraded": [_lib_change(c) for c in diff.libraries_upgraded],
            "downgraded": [_lib_change(c) for c in diff.libraries_downgraded],
        },
        "plugins": {
            "added": [_plugin_change(c) for c in diff.plugins_added],
            "removed": [_plugin_change(c) for c in diff.plugins_removed],
            "upgraded": [_plugin_change(c) for c in diff.plugins_upgraded],
            "downgraded": [_plugin_change(c) for c in diff.plugins_downgraded],
        },
        "findings": {
            "introduced": [_finding_change(f) for f in diff.findings_introduced],
            "resolved": [_finding_change(f) for f in diff.findings_resolved],
        },
    }


def _summary(diff: FreezeDiff) -> dict[str, Any]:
    return {
        "libraries": {
            "added": len(diff.libraries_added),
            "removed": len(diff.libraries_removed),
            "upgraded": len(diff.libraries_upgraded),
            "downgraded": len(diff.libraries_downgraded),
            "major": len(diff.libraries_major),
            "minor": len(diff.libraries_minor),
            "patch": len(diff.libraries_patch),
            "pre_release": len(
                [c for c in diff.library_changes if c.bump is VersionBump.PRE_RELEASE]
            ),
        },
        "plugins": {
            "added": len(diff.plugins_added),
            "removed": len(diff.plugins_removed),
            "upgraded": len(diff.plugins_upgraded),
            "downgraded": len(diff.plugins_downgraded),
        },
        "findings": {
            "introduced": len(diff.findings_introduced),
            "resolved": len(diff.findings_resolved),
        },
    }


def _lib_change(c: LibraryChange) -> dict[str, Any]:
    result: dict[str, Any] = {
        "alias": c.alias,
        "coordinate": c.coordinate,
    }
    if c.before_version is not None:
        result["before"] = c.before_version
    if c.after_version is not None:
        result["after"] = c.after_version
    if c.bump is not None:
        result["bump"] = c.bump.value
    return result


def _plugin_change(c: PluginChange) -> dict[str, Any]:
    result: dict[str, Any] = {
        "alias": c.alias,
        "plugin_id": c.plugin_id,
    }
    if c.before_version is not None:
        result["before"] = c.before_version
    if c.after_version is not None:
        result["after"] = c.after_version
    if c.bump is not None:
        result["bump"] = c.bump.value
    return result


def _finding_change(f: FindingChange) -> dict[str, Any]:
    result: dict[str, Any] = {
        "rule_id": f.rule_id,
        "severity": f.severity,
        "message": f.message,
    }
    # RFC-0016b (diff schema additive): expose the cross-section severity
    # mapping for downstream tooling. Unknown values are silently dropped so
    # forward-incompatible diffs still load.
    with contextlib.suppress(ValueError):
        result["common_severity"] = Severity(f.severity).to_common().value
    return result
