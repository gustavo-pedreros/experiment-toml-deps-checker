"""Integration-style tests for TomlCatalogParser.

Each test writes a real TOML file to tmp_path and parses it — no mocks.
"""

from pathlib import Path

import pytest

from gradle_deps_monitor.application.ports.catalog_parser import CatalogParseError
from gradle_deps_monitor.domain.version import Stability
from gradle_deps_monitor.infrastructure.parsing.toml_catalog_parser import TomlCatalogParser

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PARSER = TomlCatalogParser()


def write_toml(path: Path, content: str) -> Path:
    toml_file = path / "libs.versions.toml"
    toml_file.write_text(content, encoding="utf-8")
    return toml_file


# ---------------------------------------------------------------------------
# Happy-path: full catalog
# ---------------------------------------------------------------------------

FULL_TOML = """\
[versions]
kotlin = "2.0.0"
agp = "8.3.0-rc02"
compose = "1.6.4"

[libraries]
kotlin-stdlib = { module = "org.jetbrains.kotlin:kotlin-stdlib", version.ref = "kotlin" }
compose-ui = { group = "androidx.compose.ui", name = "ui", version.ref = "compose" }
compose-runtime = { module = "androidx.compose.runtime:runtime", version.ref = "compose" }
no-version-lib = { module = "com.example:bom-managed" }
literal-version = { module = "com.squareup.okhttp3:okhttp", version = "4.12.0" }

[plugins]
android-application = { id = "com.android.application", version.ref = "agp" }
kotlin-android = { id = "org.jetbrains.kotlin.android", version = "2.0.0" }

[bundles]
compose = ["compose-ui", "compose-runtime"]
"""


def test_parse_file_path_directly(tmp_path: Path) -> None:
    toml_file = write_toml(tmp_path, FULL_TOML)
    catalog = PARSER.parse(toml_file)
    assert catalog.source_path == toml_file


def test_parse_directory_finds_catalog(tmp_path: Path) -> None:
    write_toml(tmp_path, FULL_TOML)
    catalog = PARSER.parse(tmp_path)
    assert catalog.source_path.name == "libs.versions.toml"


def test_library_count(tmp_path: Path) -> None:
    catalog = PARSER.parse(write_toml(tmp_path, FULL_TOML))
    assert catalog.library_count == 5


def test_plugin_count(tmp_path: Path) -> None:
    catalog = PARSER.parse(write_toml(tmp_path, FULL_TOML))
    assert catalog.plugin_count == 2


def test_bundle_count(tmp_path: Path) -> None:
    catalog = PARSER.parse(write_toml(tmp_path, FULL_TOML))
    assert len(catalog.bundles) == 1


# -- Library resolution --


def test_library_version_ref_resolved(tmp_path: Path) -> None:
    catalog = PARSER.parse(write_toml(tmp_path, FULL_TOML))
    lib = catalog.library("kotlin-stdlib")
    assert lib is not None
    assert str(lib.version) == "2.0.0"
    assert lib.version.stability is Stability.STABLE


def test_library_group_name_form(tmp_path: Path) -> None:
    catalog = PARSER.parse(write_toml(tmp_path, FULL_TOML))
    lib = catalog.library("compose-ui")
    assert lib is not None
    assert lib.group == "androidx.compose.ui"
    assert lib.artifact == "ui"


def test_library_literal_version(tmp_path: Path) -> None:
    catalog = PARSER.parse(write_toml(tmp_path, FULL_TOML))
    lib = catalog.library("literal-version")
    assert lib is not None
    assert str(lib.version) == "4.12.0"


def test_library_without_version_uses_empty_string(tmp_path: Path) -> None:
    catalog = PARSER.parse(write_toml(tmp_path, FULL_TOML))
    lib = catalog.library("no-version-lib")
    assert lib is not None
    assert str(lib.version) == ""


# -- Plugin resolution --


def test_plugin_version_ref_resolved(tmp_path: Path) -> None:
    catalog = PARSER.parse(write_toml(tmp_path, FULL_TOML))
    plugin = catalog.plugin("android-application")
    assert plugin is not None
    assert str(plugin.version) == "8.3.0-rc02"
    assert plugin.version.stability is Stability.RC


def test_plugin_literal_version(tmp_path: Path) -> None:
    catalog = PARSER.parse(write_toml(tmp_path, FULL_TOML))
    plugin = catalog.plugin("kotlin-android")
    assert plugin is not None
    assert str(plugin.version) == "2.0.0"


# -- Bundle resolution --


def test_bundle_member_aliases(tmp_path: Path) -> None:
    catalog = PARSER.parse(write_toml(tmp_path, FULL_TOML))
    bundle = catalog.bundle("compose")
    assert bundle is not None
    assert set(bundle.member_aliases) == {"compose-ui", "compose-runtime"}


# ---------------------------------------------------------------------------
# Empty sections
# ---------------------------------------------------------------------------


def test_empty_catalog(tmp_path: Path) -> None:
    catalog = PARSER.parse(write_toml(tmp_path, ""))
    assert catalog.library_count == 0
    assert catalog.plugin_count == 0
    assert len(catalog.bundles) == 0


def test_only_versions_section(tmp_path: Path) -> None:
    toml = '[versions]\nkotlin = "2.0.0"\n'
    catalog = PARSER.parse(write_toml(tmp_path, toml))
    assert catalog.library_count == 0


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(CatalogParseError, match="not found"):
        PARSER.parse(tmp_path / "nonexistent.toml")


def test_missing_catalog_in_dir_raises(tmp_path: Path) -> None:
    with pytest.raises(CatalogParseError, match=r"libs\.versions\.toml"):
        PARSER.parse(tmp_path)


def test_invalid_toml_raises(tmp_path: Path) -> None:
    bad = tmp_path / "libs.versions.toml"
    bad.write_text("this is [not valid toml ===", encoding="utf-8")
    with pytest.raises(CatalogParseError, match="TOML parse error"):
        PARSER.parse(bad)


def test_unresolvable_version_ref_raises(tmp_path: Path) -> None:
    toml = """\
[libraries]
my-lib = { module = "com.example:lib", version.ref = "nonexistent" }
"""
    with pytest.raises(CatalogParseError, match=r"version\.ref 'nonexistent' not found"):
        PARSER.parse(write_toml(tmp_path, toml))


def test_library_missing_coordinate_raises(tmp_path: Path) -> None:
    toml = """\
[libraries]
bad-lib = { version = "1.0.0" }
"""
    with pytest.raises(CatalogParseError, match=r"module.*group.*name"):
        PARSER.parse(write_toml(tmp_path, toml))


def test_library_malformed_module_raises(tmp_path: Path) -> None:
    toml = """\
[libraries]
bad-lib = { module = "no-colon-here", version = "1.0.0" }
"""
    with pytest.raises(CatalogParseError, match="group:artifact"):
        PARSER.parse(write_toml(tmp_path, toml))


def test_plugin_missing_id_raises(tmp_path: Path) -> None:
    toml = """\
[plugins]
bad-plugin = { version = "1.0.0" }
"""
    with pytest.raises(CatalogParseError, match="missing or invalid 'id'"):
        PARSER.parse(write_toml(tmp_path, toml))
