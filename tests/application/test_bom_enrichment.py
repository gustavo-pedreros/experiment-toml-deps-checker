"""Unit tests for BoM enrichment (RFC-0014)."""

from __future__ import annotations

from pathlib import Path

from gradle_deps_monitor.application.bom_enrichment import enrich_catalog_with_boms
from gradle_deps_monitor.domain.bom import (
    BomResolution,
    ManagedCoordinate,
    VersionSource,
)
from gradle_deps_monitor.domain.catalog import Catalog, Library
from gradle_deps_monitor.domain.version import MavenVersion


def _lib(
    alias: str,
    group: str,
    artifact: str,
    version: str = "",
    *,
    version_ref: str | None = None,
) -> Library:
    return Library(
        alias=alias,
        group=group,
        artifact=artifact,
        version=MavenVersion(version),
        version_ref=version_ref,
    )


def _firebase_bom_resolution() -> BomResolution:
    return BomResolution(
        bom_alias="firebase-bom",
        bom_coordinate="com.google.firebase:firebase-bom",
        bom_version=MavenVersion("33.0.0"),
        managed=(
            ManagedCoordinate("com.google.firebase", "firebase-analytics", MavenVersion("21.5.0")),
            ManagedCoordinate("com.google.firebase", "firebase-auth", MavenVersion("23.0.0")),
            ManagedCoordinate(
                "com.google.firebase", "firebase-crashlytics", MavenVersion("19.0.0")
            ),
        ),
    )


def _catalog(*libs: Library) -> Catalog:
    return Catalog(
        source_path=Path("/fake/libs.versions.toml"),
        libraries=libs,
        plugins=(),
        bundles=(),
    )


# ---------------------------------------------------------------------------


def test_no_resolutions_returns_catalog_unchanged() -> None:
    catalog = _catalog(_lib("kotlin", "org.jetbrains.kotlin", "kotlin-stdlib", "2.0.0"))
    result = enrich_catalog_with_boms(catalog, ())
    assert result is catalog or result == catalog


def test_unresolved_child_gets_filled_from_bom() -> None:
    catalog = _catalog(
        _lib("firebase-bom", "com.google.firebase", "firebase-bom", "33.0.0"),
        _lib("firebase-analytics", "com.google.firebase", "firebase-analytics"),  # no version
    )
    result = enrich_catalog_with_boms(catalog, (_firebase_bom_resolution(),))

    analytics = next(lib for lib in result.libraries if lib.alias == "firebase-analytics")
    assert analytics.version.raw == "21.5.0"
    assert analytics.bom_alias == "firebase-bom"
    assert analytics.version_source == VersionSource.FROM_BOM


def test_literal_version_not_overwritten() -> None:
    """A child with an explicit version stays as-is even if the BoM manages it."""
    catalog = _catalog(
        _lib("firebase-analytics", "com.google.firebase", "firebase-analytics", "20.0.0"),
    )
    result = enrich_catalog_with_boms(catalog, (_firebase_bom_resolution(),))

    analytics = next(lib for lib in result.libraries if lib.alias == "firebase-analytics")
    assert analytics.version.raw == "20.0.0"
    assert analytics.bom_alias is None
    assert analytics.version_source == VersionSource.LITERAL


def test_unmanaged_child_stays_unresolved() -> None:
    catalog = _catalog(
        _lib("ghost", "io.example", "ghost"),  # no version, not managed by any BoM
    )
    result = enrich_catalog_with_boms(catalog, (_firebase_bom_resolution(),))
    ghost = next(lib for lib in result.libraries if lib.alias == "ghost")
    assert ghost.version.raw == ""
    assert ghost.bom_alias is None
    assert ghost.version_source == VersionSource.UNRESOLVED


def test_first_resolution_wins() -> None:
    """When two BoMs manage the same coordinate, the first listed wins."""
    other = BomResolution(
        bom_alias="alt-bom",
        bom_coordinate="com.google.firebase:alt-bom",
        bom_version=MavenVersion("99.0.0"),
        managed=(
            ManagedCoordinate("com.google.firebase", "firebase-analytics", MavenVersion("99.9.9")),
        ),
    )
    catalog = _catalog(
        _lib("firebase-analytics", "com.google.firebase", "firebase-analytics"),
    )
    # firebase-bom comes first → should win
    result = enrich_catalog_with_boms(catalog, (_firebase_bom_resolution(), other))
    analytics = next(lib for lib in result.libraries if lib.alias == "firebase-analytics")
    assert analytics.version.raw == "21.5.0"
    assert analytics.bom_alias == "firebase-bom"


def test_preserves_plugins_and_bundles() -> None:
    """Plugins, bundles, and the version map come through unchanged."""
    catalog = Catalog(
        source_path=Path("/fake/libs.versions.toml"),
        libraries=(_lib("firebase-analytics", "com.google.firebase", "firebase-analytics"),),
        plugins=(),
        bundles=(),
        versions={"kotlin": "2.0.0"},
    )
    result = enrich_catalog_with_boms(catalog, (_firebase_bom_resolution(),))
    assert result.versions == {"kotlin": "2.0.0"}
    assert result.plugins == catalog.plugins
    assert result.bundles == catalog.bundles
