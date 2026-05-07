"""Enrich a parsed catalog with BoM-resolved versions (RFC-0014).

After the parser produces a :class:`Catalog`, libraries declared
without a version look like ``MavenVersion("")``. This module walks
those entries and, when a :class:`BomResolution` provides a matching
managed coordinate, replaces them with new :class:`Library` instances
that carry the resolved version and the BoM's catalog alias.

Pure computation: no I/O. Lives in *application* because it operates
on already-built domain objects produced by the parser and the
resolver.
"""

from __future__ import annotations

from gradle_deps_monitor.domain.bom import BomResolution, ManagedCoordinate
from gradle_deps_monitor.domain.catalog import Catalog, Library


def enrich_catalog_with_boms(
    catalog: Catalog,
    resolutions: tuple[BomResolution, ...],
) -> Catalog:
    """Return a new :class:`Catalog` with BoM-resolved library entries.

    Libraries whose pinned version is empty AND whose ``group:artifact``
    appears in any :class:`BomResolution` are replaced with new
    :class:`Library` instances carrying the BoM's managed version and
    the BoM's alias as ``bom_alias``. All other libraries pass through
    unchanged.

    The first resolution that supplies a matching coordinate wins. (In
    practice catalogs do not declare two BoMs that manage the same
    artefact; if they do, this is a catalog-health concern outside the
    scope of v1.)
    """
    if not resolutions:
        return catalog

    enriched: list[Library] = []
    for lib in catalog.libraries:
        # Only libraries without a pinned version are eligible for BoM enrichment.
        if lib.version.raw or lib.bom_alias is not None:
            enriched.append(lib)
            continue

        managed = _find_managing_resolution(lib, resolutions)
        if managed is None:
            enriched.append(lib)
            continue

        bom_resolution, managed_coord = managed
        enriched.append(
            Library(
                alias=lib.alias,
                group=lib.group,
                artifact=lib.artifact,
                version=managed_coord.version,
                version_ref=lib.version_ref,
                bom_alias=bom_resolution.bom_alias,
            )
        )

    return Catalog(
        source_path=catalog.source_path,
        libraries=tuple(enriched),
        plugins=catalog.plugins,
        bundles=catalog.bundles,
        versions=catalog.versions,
    )


def _find_managing_resolution(
    lib: Library, resolutions: tuple[BomResolution, ...]
) -> tuple[BomResolution, ManagedCoordinate] | None:
    """Return ``(resolution, managed_coord)`` for the first BoM that manages *lib*."""
    for res in resolutions:
        managed = res.find(lib.group, lib.artifact)
        if managed is not None:
            return res, managed
    return None
