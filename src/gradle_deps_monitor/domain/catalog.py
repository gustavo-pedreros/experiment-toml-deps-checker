"""Gradle Version Catalog domain model.

Entities in this module are pure immutable value objects derived from
the structure of a ``libs.versions.toml`` file. No I/O; no TOML parsing.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from gradle_deps_monitor.domain.version import MavenVersion


@dataclass(frozen=True)
class Library:
    """A ``[libraries]`` entry resolved to its concrete group/artifact/version."""

    alias: str
    group: str
    artifact: str
    version: MavenVersion

    @property
    def coordinate(self) -> str:
        return f"{self.group}:{self.artifact}"

    @property
    def notation(self) -> str:
        return f"{self.group}:{self.artifact}:{self.version}"


@dataclass(frozen=True)
class Plugin:
    """A ``[plugins]`` entry resolved to its concrete id/version."""

    alias: str
    id: str
    version: MavenVersion

    @property
    def notation(self) -> str:
        return f"{self.id}:{self.version}"


@dataclass(frozen=True)
class Bundle:
    """A ``[bundles]`` entry — an ordered set of library alias references."""

    alias: str
    member_aliases: tuple[str, ...]


@dataclass(frozen=True)
class Catalog:
    """Aggregate holding all entries parsed from a single ``libs.versions.toml``.

    :param source_path: Absolute path to the TOML file that produced this catalog.
    :param libraries: All resolved library entries.
    :param plugins: All resolved plugin entries.
    :param bundles: All bundle entries (library alias groupings).
    """

    source_path: Path
    libraries: tuple[Library, ...]
    plugins: tuple[Plugin, ...]
    bundles: tuple[Bundle, ...]

    def library(self, alias: str) -> Library | None:
        """Return the library with the given alias, or ``None``."""
        return next((lib for lib in self.libraries if lib.alias == alias), None)

    def plugin(self, alias: str) -> Plugin | None:
        """Return the plugin with the given alias, or ``None``."""
        return next((p for p in self.plugins if p.alias == alias), None)

    def bundle(self, alias: str) -> Bundle | None:
        """Return the bundle with the given alias, or ``None``."""
        return next((b for b in self.bundles if b.alias == alias), None)

    @property
    def library_count(self) -> int:
        return len(self.libraries)

    @property
    def plugin_count(self) -> int:
        return len(self.plugins)
