"""Bill of Materials (BoM) domain model (RFC-0014).

Maven BoMs (and Gradle ``platform`` artifacts) declare a set of
managed dependencies — group / artifact / version triples that
client catalogs can pull in **without restating the version**. The
canonical Android examples are:

- ``com.google.firebase:firebase-bom`` → drives every ``firebase-*`` artefact
- ``androidx.compose:compose-bom`` → drives every ``androidx.compose.*`` artefact
- ``com.squareup.okhttp3:okhttp-bom``
- ``com.squareup.retrofit2:retrofit-bom``

This module captures the minimal value objects needed to reason
about that relationship at freeze time. Resolving a BoM (fetching
its POM and parsing ``<dependencyManagement>``) is an infrastructure
concern; this domain only describes the result.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from gradle_deps_monitor.domain.version import MavenVersion


class VersionSource(StrEnum):
    """Where a library's effective version came from.

    Derived view over :class:`~gradle_deps_monitor.domain.catalog.Library`
    fields. Reports use this label so consumers can group / filter
    libraries by the *origin* of their version pin without having to
    inspect three structural fields.
    """

    LITERAL = "literal"  # version "X.Y.Z" inline in [libraries]
    VERSION_REF = "version-ref"  # version.ref = "kotlin"
    FROM_BOM = "from-bom"  # version supplied by a resolved BoM
    UNRESOLVED = "unresolved"  # no version declared and no BoM provided one


@dataclass(frozen=True)
class ManagedCoordinate:
    """One ``<dependency>`` row inside a BoM's ``<dependencyManagement>``."""

    group: str
    artifact: str
    version: MavenVersion

    @property
    def coordinate(self) -> str:
        return f"{self.group}:{self.artifact}"


@dataclass(frozen=True)
class BomResolution:
    """The result of resolving one BoM library to its managed dependency set.

    Attributes:
        bom_alias:      Catalog alias of the BoM library entry.
        bom_coordinate: ``"group:artifact"`` of the BoM itself.
        bom_version:    Pinned version of the BoM (drives every managed lib).
        managed:        Coordinates published in
                        ``<dependencyManagement><dependencies>``.
    """

    bom_alias: str
    bom_coordinate: str
    bom_version: MavenVersion
    managed: tuple[ManagedCoordinate, ...]

    def find(self, group: str, artifact: str) -> ManagedCoordinate | None:
        """Return the managed entry for *group:artifact*, or ``None``."""
        return next(
            (m for m in self.managed if m.group == group and m.artifact == artifact),
            None,
        )
