"""TOML-backed implementation of the CatalogParser port."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from gradle_deps_monitor.application.ports.catalog_parser import CatalogParseError
from gradle_deps_monitor.domain import Bundle, Catalog, Library, Plugin
from gradle_deps_monitor.domain.rich_version import RichVersion
from gradle_deps_monitor.domain.version import MavenVersion

# Rich-version keys recognised in a TOML version table (RFC-0020).
_RICH_KEYS: frozenset[str] = frozenset({"strictly", "require", "prefer", "reject"})

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

        versions: dict[str, str] = _parse_versions_map(data.get("versions", {}))
        libraries = self._parse_libraries(data.get("libraries", {}), versions)
        plugins = self._parse_plugins(data.get("plugins", {}), versions)
        bundles = self._parse_bundles(data.get("bundles", {}))

        return Catalog(
            source_path=toml_path,
            libraries=tuple(libraries),
            plugins=tuple(plugins),
            bundles=tuple(bundles),
            versions=dict(versions),
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
            version, version_ref, constraints = _resolve_version(
                alias, entry.get("version"), versions, "[libraries]"
            )
            libraries.append(
                Library(
                    alias=alias,
                    group=group,
                    artifact=artifact,
                    version=version,
                    version_ref=version_ref,
                    version_constraints=constraints,
                )
            )
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
            # Plugins share the same parser path as libraries to fix the
            # rich-version crash, but for the tracer they discard the
            # rich-version metadata. Surfacing Plugin.version_constraints
            # is a Phase 3 follow-up of RFC-0020.
            version, version_ref, _ = _resolve_version(
                alias, entry.get("version"), versions, "[plugins]"
            )
            plugins.append(
                Plugin(alias=alias, id=plugin_id, version=version, version_ref=version_ref)
            )
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
) -> tuple[MavenVersion, str | None, RichVersion | None]:
    """Resolve a TOML version field to ``(MavenVersion, version_ref, constraints)``.

    The field can be:

    - absent (BoM-managed)
    - a literal string
    - a table with a ``ref`` key pointing to ``[versions]``
    - a table with one or more rich-version keys (``strictly`` /
      ``require`` / ``prefer`` / ``reject``), per RFC-0020

    Returns a triple:

    - ``MavenVersion``: the effective version for comparisons / drift.
    - ``version_ref``: the ``[versions]`` key used, or ``None`` for
      inline / absent / rich.
    - ``constraints``: a :class:`RichVersion` when the table used any
      rich key, else ``None``. The invariant
      ``constraints.effective == returned_version`` always holds.
    """
    if version_field is None:
        return MavenVersion(""), None, None
    if isinstance(version_field, str):
        return MavenVersion(version_field), None, None
    if isinstance(version_field, dict):
        return _resolve_version_table(alias, version_field, versions, section)
    raise CatalogParseError(
        f"{section} '{alias}': unexpected version type '{type(version_field).__name__}'"
    )


def _resolve_version_table(
    alias: str,
    table: dict[str, Any],
    versions: dict[str, str],
    section: str,
) -> tuple[MavenVersion, str | None, RichVersion | None]:
    """Resolve a version *table*: either ``{ref}`` or rich-version keys.

    The two forms are mutually exclusive in this tracer. Mixing
    ``ref`` with rich-version keys raises :class:`CatalogParseError`;
    Phase 2 of RFC-0020 may revisit that policy after sampling real
    catalogs.
    """
    ref = table.get("ref")
    rich_keys_present = _RICH_KEYS.intersection(table.keys())

    if ref is not None and rich_keys_present:
        raise CatalogParseError(
            f"{section} '{alias}': combining 'ref' with rich-version keys "
            f"({', '.join(sorted(rich_keys_present))}) is not supported"
        )

    if rich_keys_present:
        constraints = _build_rich_version_from_table(alias, table, section)
        return constraints.effective, None, constraints

    if isinstance(ref, str):
        resolved = versions.get(ref)
        if resolved is None:
            raise CatalogParseError(
                f"{section} '{alias}': version.ref '{ref}' not found in [versions]"
            )
        return MavenVersion(resolved), ref, None

    # Empty table or table with only unknown keys.
    raise CatalogParseError(
        f"{section} '{alias}': version table has no 'ref' key and no rich-version keys "
        f"({', '.join(sorted(_RICH_KEYS))})"
    )


def _build_rich_version_from_table(
    alias: str,
    table: dict[str, Any],
    section: str,
) -> RichVersion:
    """Build a :class:`RichVersion` from a TOML rich-version table.

    Validates the type of each recognised key and rejects anything
    unparseable with a useful, section-aware error message. Shared by
    the ``[libraries]``/``[plugins]`` version-field parser and the
    top-level ``[versions]`` map parser.
    """
    strictly = _expect_optional_str(table, "strictly", alias, section)
    require = _expect_optional_str(table, "require", alias, section)
    prefer = _expect_optional_str(table, "prefer", alias, section)
    reject = _expect_optional_str_list(table, "reject", alias, section)

    return RichVersion(
        strictly=strictly,
        require=require,
        prefer=prefer,
        reject=reject,
    )


def _expect_optional_str(table: dict[str, Any], key: str, alias: str, section: str) -> str | None:
    value = table.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise CatalogParseError(
            f"{section} '{alias}': rich-version key '{key}' must be a string, "
            f"got '{type(value).__name__}'"
        )
    return value


def _expect_optional_str_list(
    table: dict[str, Any], key: str, alias: str, section: str
) -> tuple[str, ...]:
    value = table.get(key)
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise CatalogParseError(
            f"{section} '{alias}': rich-version key '{key}' must be a list of strings"
        )
    return tuple(value)


def _parse_versions_map(value: Any) -> dict[str, str]:
    """Parse the top-level ``[versions]`` map.

    Accepts two value shapes per key (RFC-0020):

    - **string** — the canonical form (``kotlin = "2.0.0"``).
    - **rich-version table** — one or more of ``strictly`` / ``require`` /
      ``prefer`` / ``reject`` (``kotlin = { strictly = "2.0.0" }``).

    Rich tables are flattened to their *effective* version per
    :class:`RichVersion` precedence (``strictly`` > ``require`` >
    ``prefer``). A reject-only entry resolves to the empty-string
    sentinel, which mirrors the BoM-managed convention and excludes the
    key from drift analysis.

    This preserves ``Catalog.versions``'s ``dict[str, str]`` contract:
    every downstream consumer (catalog health rules, ``version.ref``
    resolution, toolchain checker) keeps seeing plain strings, while
    catalogs that pin toolchains via rich tables no longer crash.
    """
    if not isinstance(value, dict):
        raise CatalogParseError("[versions] must be a table")

    resolved: dict[str, str] = {}
    for key, raw in value.items():
        if isinstance(raw, str):
            resolved[key] = raw
            continue
        if isinstance(raw, dict):
            rich_keys_present = _RICH_KEYS.intersection(raw.keys())
            if not rich_keys_present:
                raise CatalogParseError(
                    f"[versions] '{key}': version table has no rich-version keys "
                    f"({', '.join(sorted(_RICH_KEYS))})"
                )
            constraints = _build_rich_version_from_table(key, raw, "[versions]")
            resolved[key] = constraints.effective.raw
            continue
        raise CatalogParseError(
            f"[versions] '{key}': expected a string or rich-version table, "
            f"got '{type(raw).__name__}'"
        )
    return resolved
