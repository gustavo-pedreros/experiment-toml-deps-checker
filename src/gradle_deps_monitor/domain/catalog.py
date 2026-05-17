"""Gradle Version Catalog domain model.

Entities in this module are pure immutable value objects derived from
the structure of a ``libs.versions.toml`` file. No I/O; no TOML parsing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from gradle_deps_monitor.domain.bom import VersionSource
from gradle_deps_monitor.domain.rich_version import RichVersion
from gradle_deps_monitor.domain.version import MavenVersion

# Suffixes that mark a library entry as a BoM by convention. The optional
# trailing ``-<word>`` group catches Compose-style alpha BoM lines
# (``compose-bom-alpha``) and any future suffix variants — issue #15 from
# the 2026-05 stress test menu. False positives are unlikely because the
# trailing group requires a hyphen separator.
_BOM_ARTIFACT_RE = re.compile(r"(?:-bom|-platform)(?:-[a-z0-9]+)?$", re.IGNORECASE)


@dataclass(frozen=True)
class Library:
    """A ``[libraries]`` entry resolved to its concrete group/artifact/version."""

    alias: str
    group: str
    artifact: str
    version: MavenVersion
    #: Name of the ``[versions]`` key used via ``version.ref``, or ``None``
    #: when the version is declared inline or absent (BoM-managed).
    version_ref: str | None = None
    #: Catalog alias of the BoM that supplies this library's version, or
    #: ``None`` when the version did not come from a BoM. Set by the
    #: BoM-resolution step in
    #: :class:`~gradle_deps_monitor.application.generate_freeze_report.GenerateFreezeReport`.
    bom_alias: str | None = None
    #: Rich-version declaration (``strictly`` / ``require`` / ``prefer`` /
    #: ``reject``) when the catalog used one. ``None`` for plain-string
    #: versions, ``version.ref`` lookups, and BoM-managed entries. See
    #: RFC-0020. When set, ``version_constraints.effective`` MUST equal
    #: ``version`` — enforced in :meth:`__post_init__`.
    version_constraints: RichVersion | None = None

    def __post_init__(self) -> None:
        if self.version_constraints is None:
            return
        effective = self.version_constraints.effective
        if effective != self.version:
            raise ValueError(
                f"Library '{self.alias}': version_constraints.effective "
                f"('{effective.raw}') must equal version ('{self.version.raw}')"
            )

    @property
    def coordinate(self) -> str:
        return f"{self.group}:{self.artifact}"

    @property
    def notation(self) -> str:
        return f"{self.group}:{self.artifact}:{self.version}"

    @property
    def is_bom_candidate(self) -> bool:
        """``True`` when the artifact name marks this entry as a Maven BoM.

        Matches the canonical suffixes ``-bom`` / ``-platform`` plus any
        single trailing release-line modifier (``-bom-alpha``,
        ``-platform-beta``, etc.). See :data:`_BOM_ARTIFACT_RE`.
        """
        return bool(_BOM_ARTIFACT_RE.search(self.artifact))

    @property
    def version_source(self) -> VersionSource:
        """Where this library's effective version came from. Derived (RFC-0014)."""
        if self.bom_alias is not None:
            return VersionSource.FROM_BOM
        if self.version_ref is not None:
            return VersionSource.VERSION_REF
        if self.version.raw:
            return VersionSource.LITERAL
        return VersionSource.UNRESOLVED


@dataclass(frozen=True)
class Plugin:
    """A ``[plugins]`` entry resolved to its concrete id/version."""

    alias: str
    id: str
    version: MavenVersion
    #: Name of the ``[versions]`` key used via ``version.ref``, or ``None``
    #: when the version is declared inline or absent.
    version_ref: str | None = None

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
    :param versions: Raw ``[versions]`` map (key → version string). Used by
        catalog health rules; excluded from equality and hashing so that the
        frozen dataclass can include a mutable dict without breaking ``__hash__``.
    """

    source_path: Path
    libraries: tuple[Library, ...]
    plugins: tuple[Plugin, ...]
    bundles: tuple[Bundle, ...]
    versions: dict[str, str] = field(
        default_factory=dict,
        compare=False,
        hash=False,
    )

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
