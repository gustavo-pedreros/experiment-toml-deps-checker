"""SnapshotLoader port and FreezeSnapshot DTO.

A :class:`FreezeSnapshot` is a lightweight, JSON-friendly representation of a
previously written freeze report.  It carries only the data needed to compute
a :class:`~gradle_deps_monitor.domain.diff.FreezeDiff`; it does not reproduce
the full domain object graph.

:class:`SnapshotLoader` is the port (Protocol) that infrastructure adapters
implement.  The only shipped adapter is
:class:`~gradle_deps_monitor.infrastructure.loaders.json_snapshot_loader.JsonSnapshotLoader`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

# ---------------------------------------------------------------------------
# DTO
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LibrarySnapshot:
    """Lightweight representation of a library entry from a freeze report.

    :param alias:      Catalog alias (e.g. ``core-ktx``).
    :param coordinate: Maven coordinate ``group:artifact``.
    :param version:    Raw version string.
    """

    alias: str
    coordinate: str
    version: str


@dataclass(frozen=True)
class PluginSnapshot:
    """Lightweight representation of a plugin entry from a freeze report.

    :param alias:     Catalog alias (e.g. ``kotlin-android``).
    :param plugin_id: Gradle plugin id.
    :param version:   Raw version string.
    """

    alias: str
    plugin_id: str
    version: str


@dataclass(frozen=True)
class FindingSnapshot:
    """Lightweight representation of a health finding from a freeze report.

    :param rule_id:  Rule identifier (e.g. ``HDX-001``).
    :param severity: Severity string (``error``, ``warning``, ``info``, ``suggestion``).
    :param message:  Human-readable description.
    """

    rule_id: str
    severity: str
    message: str


@dataclass(frozen=True)
class FreezeSnapshot:
    """Lightweight, loader-agnostic view of a previously written freeze report.

    :param schema_version: JSON schema version string (currently ``"1"``).
    :param generated_at:   Timestamp at which the original report was generated.
    :param source_path:    Path of the ``libs.versions.toml`` that produced the report.
    :param libraries:      All library entries.
    :param plugins:        All plugin entries.
    :param findings:       All health findings.
    """

    schema_version: str
    generated_at: datetime
    source_path: str
    libraries: tuple[LibrarySnapshot, ...]
    plugins: tuple[PluginSnapshot, ...]
    findings: tuple[FindingSnapshot, ...]


# ---------------------------------------------------------------------------
# Port
# ---------------------------------------------------------------------------


class SnapshotLoader(Protocol):
    """Load a previously written freeze report from persistent storage."""

    def load(self, path: Path) -> FreezeSnapshot:
        """Read *path* and return a :class:`FreezeSnapshot`.

        :param path: Path to a freeze report file (e.g. ``freeze.json``).
        :raises FileNotFoundError: If *path* does not exist.
        :raises ValueError: If the file cannot be parsed or has an unsupported
            schema version.
        """
        ...
