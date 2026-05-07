"""Unit tests for the BoM domain model (RFC-0014)."""

from __future__ import annotations

import pytest

from gradle_deps_monitor.domain.bom import (
    BomResolution,
    ManagedCoordinate,
    VersionSource,
)
from gradle_deps_monitor.domain.catalog import Library
from gradle_deps_monitor.domain.version import MavenVersion


def _mc(group: str, artifact: str, version: str) -> ManagedCoordinate:
    return ManagedCoordinate(group=group, artifact=artifact, version=MavenVersion(version))


# ---------------------------------------------------------------------------
# ManagedCoordinate
# ---------------------------------------------------------------------------


class TestManagedCoordinate:
    def test_coordinate_property(self) -> None:
        m = _mc("com.example", "lib", "1.0.0")
        assert m.coordinate == "com.example:lib"


# ---------------------------------------------------------------------------
# BomResolution
# ---------------------------------------------------------------------------


class TestBomResolution:
    def _resolution(self) -> BomResolution:
        return BomResolution(
            bom_alias="firebase-bom",
            bom_coordinate="com.google.firebase:firebase-bom",
            bom_version=MavenVersion("33.0.0"),
            managed=(
                _mc("com.google.firebase", "firebase-analytics", "21.5.0"),
                _mc("com.google.firebase", "firebase-auth", "23.0.0"),
            ),
        )

    def test_find_existing(self) -> None:
        res = self._resolution()
        m = res.find("com.google.firebase", "firebase-analytics")
        assert m is not None
        assert m.version.raw == "21.5.0"

    def test_find_missing(self) -> None:
        res = self._resolution()
        assert res.find("com.example", "ghost") is None


# ---------------------------------------------------------------------------
# Library.is_bom_candidate
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "artifact,expected",
    [
        ("firebase-bom", True),
        ("compose-bom", True),
        ("okhttp-bom", True),
        ("retrofit-bom", True),
        ("kotlin-stdlib-platform", True),
        ("kotlin-stdlib", False),
        ("retrofit", False),
        ("okhttp", False),
        # No suffix collision (BoM-like substring but not at end)
        ("bombast", False),
    ],
)
def test_library_is_bom_candidate(artifact: str, expected: bool) -> None:
    lib = Library(alias="x", group="com.example", artifact=artifact, version=MavenVersion("1.0.0"))
    assert lib.is_bom_candidate is expected


# ---------------------------------------------------------------------------
# Library.version_source (derived)
# ---------------------------------------------------------------------------


class TestLibraryVersionSource:
    def test_literal(self) -> None:
        lib = Library(alias="x", group="g", artifact="a", version=MavenVersion("1.0.0"))
        assert lib.version_source == VersionSource.LITERAL

    def test_version_ref(self) -> None:
        lib = Library(
            alias="x",
            group="g",
            artifact="a",
            version=MavenVersion("1.0.0"),
            version_ref="kotlin",
        )
        assert lib.version_source == VersionSource.VERSION_REF

    def test_from_bom_takes_priority(self) -> None:
        lib = Library(
            alias="x",
            group="g",
            artifact="a",
            version=MavenVersion("21.5.0"),
            bom_alias="firebase-bom",
        )
        assert lib.version_source == VersionSource.FROM_BOM

    def test_unresolved(self) -> None:
        lib = Library(alias="x", group="g", artifact="a", version=MavenVersion(""))
        assert lib.version_source == VersionSource.UNRESOLVED
