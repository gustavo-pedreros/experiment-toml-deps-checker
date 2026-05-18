"""MavenBomResolver — fetches BoM POMs and parses dependencyManagement (RFC-0014).

Routing mirrors :class:`MavenVersionStatusResolver`: BoMs published
under ``androidx.*`` / ``com.google.*`` / ``com.android.*`` are tried
on Google Maven first, everything else on Maven Central first.
On a 404 the resolver falls back to the secondary registry. Any
per-BoM error (network, malformed XML) skips the BoM rather than
aborting the run.
"""

from __future__ import annotations

import asyncio
import xml.etree.ElementTree as ET

import httpx

from gradle_deps_monitor.domain.bom import BomResolution, ManagedCoordinate
from gradle_deps_monitor.domain.catalog import Library
from gradle_deps_monitor.domain.version import MavenVersion
from gradle_deps_monitor.infrastructure._shared.http import HttpPolicy, make_resilient_client

_GOOGLE_PREFIXES: tuple[str, ...] = ("androidx.", "com.google.", "com.android.")
_MAVEN_CENTRAL = "https://repo1.maven.org/maven2"
_GOOGLE_MAVEN = "https://dl.google.com/dl/android/maven2"

# Maven 4 POM namespace prefix that ElementTree includes in tag names. Maven
# does not always declare it, so we strip it defensively.
_POM_NS = "{http://maven.apache.org/POM/4.0.0}"


class MavenBomResolver:
    """Concrete :class:`~...application.ports.bom_resolver.BomResolver`."""

    async def resolve(self, boms: tuple[Library, ...]) -> tuple[BomResolution, ...]:
        if not boms:
            return ()

        # RFC-0030: resilient transport. Matches MavenVersionStatusResolver's
        # 10 s timeout — both adapters hit the same registries from the same
        # use case.
        async with make_resilient_client(policy=HttpPolicy(timeout_seconds=10.0)) as client:
            tasks = [self._resolve_one(bom, client) for bom in boms]
            results = await asyncio.gather(*tasks, return_exceptions=False)

        return tuple(r for r in results if r is not None)

    async def _resolve_one(
        self,
        bom: Library,
        client: httpx.AsyncClient,
    ) -> BomResolution | None:
        if not bom.version.raw:
            # We cannot fetch a POM without a version. UNRESOLVED BoMs
            # (rare; would mean a BoM nested inside another BoM that we
            # haven't resolved yet) just get skipped for v1.
            return None

        pom_text = await self._fetch_pom(client, bom.group, bom.artifact, bom.version.raw)
        if pom_text is None:
            return None

        try:
            managed = _parse_managed(pom_text)
        except ET.ParseError:
            return None

        return BomResolution(
            bom_alias=bom.alias,
            bom_coordinate=bom.coordinate,
            bom_version=bom.version,
            managed=tuple(managed),
        )

    async def _fetch_pom(
        self,
        client: httpx.AsyncClient,
        group: str,
        artifact: str,
        version: str,
    ) -> str | None:
        primary, secondary = self._registries_for(group)
        for base in (primary, secondary):
            url = self._pom_url(base, group, artifact, version)
            try:
                response = await client.get(url, follow_redirects=True)
            except httpx.RequestError:
                continue
            if response.status_code == 200:
                return response.text
            if response.status_code == 404:
                continue
            # Other status: skip both registries.
            return None
        return None

    @staticmethod
    def _registries_for(group: str) -> tuple[str, str]:
        if any(group == p.rstrip(".") or group.startswith(p) for p in _GOOGLE_PREFIXES):
            return _GOOGLE_MAVEN, _MAVEN_CENTRAL
        return _MAVEN_CENTRAL, _GOOGLE_MAVEN

    @staticmethod
    def _pom_url(base: str, group: str, artifact: str, version: str) -> str:
        return f"{base}/{group.replace('.', '/')}/{artifact}/{version}/{artifact}-{version}.pom"


# ---------------------------------------------------------------------------
# POM parsing
# ---------------------------------------------------------------------------


def _parse_managed(pom_text: str) -> list[ManagedCoordinate]:
    """Extract ``<dependencyManagement><dependencies>`` entries from a POM."""
    root = ET.fromstring(pom_text)

    dep_mgmt = _find_child(root, "dependencyManagement")
    if dep_mgmt is None:
        return []
    deps = _find_child(dep_mgmt, "dependencies")
    if deps is None:
        return []

    managed: list[ManagedCoordinate] = []
    for dep in deps:
        if not dep.tag.endswith("dependency"):
            continue
        group = _child_text(dep, "groupId")
        artifact = _child_text(dep, "artifactId")
        version = _child_text(dep, "version")
        if not (group and artifact and version):
            continue
        # Skip "import" scope BoMs — they don't pin children, they aggregate
        # other BoMs. Out of scope for v1; we only resolve the top-level set.
        scope = _child_text(dep, "scope")
        if scope == "import":
            continue
        managed.append(
            ManagedCoordinate(
                group=group,
                artifact=artifact,
                version=MavenVersion(version),
            )
        )
    return managed


def _find_child(elem: ET.Element, tag: str) -> ET.Element | None:
    direct = elem.find(tag)
    if direct is not None:
        return direct
    return elem.find(f"{_POM_NS}{tag}")


def _child_text(elem: ET.Element, tag: str) -> str | None:
    child = _find_child(elem, tag)
    if child is None or child.text is None:
        return None
    return child.text.strip() or None
