"""TOML-backed implementation of the CatalogParser port."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from gradle_deps_monitor.application.ports.catalog_parser import CatalogParseError
from gradle_deps_monitor.domain import Bundle, Catalog, Library, Plugin
from gradle_deps_monitor.domain.version import MavenVersion

# Gradle Version Catalog conventional filename.
_CATALOG_FILENAME = "libs.versions.toml"


class TomlCatalogParser:
    """Reads a ``libs.versions.toml`` and returns a :class:`~gradle_deps_monitor.domain.Catalog`.

    Accepts either:
    - The path to the TOML file directly.
    - The directory that contains ``libs.versions.toml`` (conventional Gradle layout).
    """

    def parse(self, path: Path) -> Catalog:
        """Parse *path* into a :class:`~gradle_deps_monitor.domain.Catalog`.

        :raises CatalogParseError: On missing file, TOML syntax error, or
            unresolvable ``version.ref``.
        """
        toml_path = self._resolve_path(path)
        data = self._load(toml_path)

        versions: dict[str, str] = _expect_str_map(data.get("versions", {}), "versions")
        libraries = self._parse_libraries(data.get("libraries", {}), versions)
        plugins = self._parse_plugins(data.get("plugins", {}), versions)
        bundles = self._parse_bundles(data.get("bundles", {}))

        return Catalog(
            source_path=toml_path,
            libraries=tuple(libraries),
            plugins=tuple(plugins),
            bundles=tuple(bundles),
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_path(path: Path) -> Path:
        if path.is_dir():
            candidate = path / _CATALOG_FILENAME
            if not candidate.exists():
                raise CatalogParseError(f"No '{_CATALOG_FILENAME}' found in directory: {path}")
            return candidate
        if not path.exists():
            raise CatalogParseError(f"Catalog file not found: {path}")
        return path

    @staticmethod
    def _load(path: Path) -> dict[str, Any]:
        try:
            with path.open("rb") as fh:
                return tomllib.load(fh)
        except tomllib.TOMLDecodeError as exc:
            raise CatalogParseError(f"TOML parse error in {path}: {exc}") from exc

    def _parse_libraries(
        self,
        raw: dict[str, Any],
        versions: dict[str, str],
    ) -> list[Library]:
        libraries: list[Library] = []
        for alias, entry in raw.items():
            if not isinstance(entry, dict):
                raise CatalogParseError(
                    f"[libraries] '{alias}': expected a table, got {type(entry).__name__}"
                )
            group, artifact = _parse_coordinate(alias, entry)
            version = _resolve_version(alias, entry.get("version"), versions, "[libraries]")
            libraries.append(Library(alias=alias, group=group, artifact=artifact, version=version))
        return libraries

    def _parse_plugins(
        self,
        raw: dict[str, Any],
        versions: dict[str, str],
    ) -> list[Plugin]:
        plugins: list[Plugin] = []
        for alias, entry in raw.items():
            if not isinstance(entry, dict):
                raise CatalogParseError(
                    f"[plugins] '{alias}': expected a table, got {type(entry).__name__}"
                )
            plugin_id = entry.get("id")
            if not isinstance(plugin_id, str):
                raise CatalogParseError(f"[plugins] '{alias}': missing or invalid 'id' field")
            version = _resolve_version(alias, entry.get("version"), versions, "[plugins]")
            plugins.append(Plugin(alias=alias, id=plugin_id, version=version))
        return plugins

    @staticmethod
    def _parse_bundles(raw: dict[str, Any]) -> list[Bundle]:
        bundles: list[Bundle] = []
        for alias, members in raw.items():
            if not isinstance(members, list) or not all(isinstance(m, str) for m in members):
                raise CatalogParseError(f"[bundles] '{alias}': expected a list of strings")
            bundles.append(Bundle(alias=alias, member_aliases=tuple(members)))
        return bundles


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _parse_coordinate(alias: str, entry: dict[str, Any]) -> tuple[str, str]:
    """Return (group, artifact) from either ``module`` or ``group``+``name``."""
    module: str | None = entry.get("module")
    if isinstance(module, str):
        parts = module.split(":", 1)
        if len(parts) != 2 or not all(parts):
            raise CatalogParseError(
                f"[libraries] '{alias}': 'module' must be 'group:artifact', got '{module}'"
            )
        return parts[0], parts[1]

    group: str | None = entry.get("group")
    name: str | None = entry.get("name")
    if isinstance(group, str) and isinstance(name, str) and group and name:
        return group, name

    raise CatalogParseError(
        f"[libraries] '{alias}': must define either 'module' or both 'group' and 'name'"
    )


def _resolve_version(
    alias: str,
    version_field: Any,
    versions: dict[str, str],
    section: str,
) -> MavenVersion:
    """Resolve a TOML version field to a :class:`MavenVersion`.

    The field can be absent (BOM-managed), a literal string, or a table
    with a ``ref`` key pointing to ``[versions]``.
    """
    if version_field is None:
        return MavenVersion("")
    if isinstance(version_field, str):
        return MavenVersion(version_field)
    if isinstance(version_field, dict):
        ref: str | None = version_field.get("ref")
        if not isinstance(ref, str):
            raise CatalogParseError(f"{section} '{alias}': version table has no 'ref' key")
        resolved = versions.get(ref)
        if resolved is None:
            raise CatalogParseError(
                f"{section} '{alias}': version.ref '{ref}' not found in [versions]"
            )
        return MavenVersion(resolved)
    raise CatalogParseError(
        f"{section} '{alias}': unexpected version type '{type(version_field).__name__}'"
    )


def _expect_str_map(value: Any, section: str) -> dict[str, str]:
    if not isinstance(value, dict):
        raise CatalogParseError(f"[{section}] must be a table")
    bad = {k: v for k, v in value.items() if not isinstance(v, str)}
    if bad:
        keys = ", ".join(bad)
        raise CatalogParseError(f"[{section}] non-string values for keys: {keys}")
    return value
