"""Unit tests for the 8 built-in catalog health rules.

Each rule has at least one positive test (finding expected) and one negative
test (no findings expected), as required by RFC-0011.
"""

from __future__ import annotations

from pathlib import Path

from gradle_deps_monitor.checks.catalog_health import (
    duplicate_library,
    duplicate_version_values,
    inconsistent_naming,
    inline_versions,
    missing_bundles,
    missing_plugins,
    orphan_version_ref,
    unresolved_version_ref,
)
from gradle_deps_monitor.domain import Severity
from gradle_deps_monitor.domain.catalog import Bundle, Catalog, Library, Plugin
from gradle_deps_monitor.domain.version import MavenVersion

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PATH = Path("/fake/libs.versions.toml")


def _lib(
    alias: str,
    group: str = "com.example",
    artifact: str | None = None,
    version: str = "1.0.0",
    version_ref: str | None = None,
) -> Library:
    return Library(
        alias=alias,
        group=group,
        artifact=artifact or alias,
        version=MavenVersion(version),
        version_ref=version_ref,
    )


def _plugin(
    alias: str,
    plugin_id: str | None = None,
    version: str = "1.0.0",
    version_ref: str | None = None,
) -> Plugin:
    return Plugin(
        alias=alias,
        id=plugin_id or alias,
        version=MavenVersion(version),
        version_ref=version_ref,
    )


def _catalog(
    libraries: tuple[Library, ...] = (),
    plugins: tuple[Plugin, ...] = (),
    bundles: tuple[Bundle, ...] = (),
    versions: dict[str, str] | None = None,
) -> Catalog:
    return Catalog(
        source_path=_PATH,
        libraries=libraries,
        plugins=plugins,
        bundles=bundles,
        versions=versions or {},
    )


# ---------------------------------------------------------------------------
# catalog.missing-plugins
# ---------------------------------------------------------------------------


def test_missing_plugins_fires_when_no_plugins() -> None:
    cat = _catalog(libraries=(_lib("core-ktx"),))
    findings = missing_plugins.check(cat)
    assert len(findings) == 1
    assert findings[0].rule_id == missing_plugins.ID
    assert findings[0].severity == Severity.WARNING


def test_missing_plugins_silent_when_plugins_present() -> None:
    cat = _catalog(plugins=(_plugin("agp"),))
    assert missing_plugins.check(cat) == []


def test_missing_plugins_silent_on_empty_catalog() -> None:
    assert missing_plugins.check(_catalog()) == []


# ---------------------------------------------------------------------------
# catalog.inline-versions
# ---------------------------------------------------------------------------


def test_inline_versions_fires_for_library_with_inline_version() -> None:
    cat = _catalog(libraries=(_lib("core-ktx", version="1.13.0", version_ref=None),))
    findings = inline_versions.check(cat)
    assert len(findings) == 1
    assert findings[0].rule_id == inline_versions.ID
    assert findings[0].severity == Severity.INFO
    assert "core-ktx" in findings[0].details


def test_inline_versions_fires_for_plugin_with_inline_version() -> None:
    cat = _catalog(plugins=(_plugin("agp", version="8.0.0", version_ref=None),))
    assert len(inline_versions.check(cat)) == 1


def test_inline_versions_silent_when_all_use_refs() -> None:
    cat = _catalog(
        libraries=(_lib("core-ktx", version_ref="androidxCore"),),
        plugins=(_plugin("agp", version_ref="agp"),),
        versions={"androidxCore": "1.13.0", "agp": "8.0.0"},
    )
    assert inline_versions.check(cat) == []


def test_inline_versions_silent_for_absent_version() -> None:
    # version="" means BOM-managed — not considered inline
    cat = _catalog(libraries=(_lib("bom-lib", version="", version_ref=None),))
    assert inline_versions.check(cat) == []


def test_inline_versions_message_truncates_long_lists() -> None:
    libs = tuple(_lib(f"lib-{i}") for i in range(6))
    findings = inline_versions.check(_catalog(libraries=libs))
    assert len(findings) == 1
    assert "and 3 more" in findings[0].details


# ---------------------------------------------------------------------------
# catalog.missing-bundles
# ---------------------------------------------------------------------------


def test_missing_bundles_fires_for_multi_library_catalog() -> None:
    cat = _catalog(libraries=(_lib("a"), _lib("b")))
    findings = missing_bundles.check(cat)
    assert len(findings) == 1
    assert findings[0].rule_id == missing_bundles.ID
    assert findings[0].severity == Severity.INFO


def test_missing_bundles_silent_when_bundles_present() -> None:
    cat = _catalog(
        libraries=(_lib("a"), _lib("b")),
        bundles=(Bundle("compose", ("a", "b")),),
    )
    assert missing_bundles.check(cat) == []


def test_missing_bundles_silent_for_single_library() -> None:
    assert missing_bundles.check(_catalog(libraries=(_lib("only"),))) == []


def test_missing_bundles_silent_for_empty_catalog() -> None:
    assert missing_bundles.check(_catalog()) == []


# ---------------------------------------------------------------------------
# catalog.duplicate-version-values
# ---------------------------------------------------------------------------


def test_duplicate_version_values_fires_when_two_keys_share_value() -> None:
    cat = _catalog(versions={"kotlin": "2.0.0", "kotlinPlugin": "2.0.0"})
    findings = duplicate_version_values.check(cat)
    assert len(findings) == 1
    assert findings[0].rule_id == duplicate_version_values.ID
    assert findings[0].severity == Severity.SUGGESTION
    assert "2.0.0" in findings[0].message


def test_duplicate_version_values_emits_one_finding_per_duplicate_group() -> None:
    cat = _catalog(versions={"a": "1.0", "b": "1.0", "x": "2.0", "y": "2.0"})
    assert len(duplicate_version_values.check(cat)) == 2


def test_duplicate_version_values_silent_when_all_unique() -> None:
    cat = _catalog(versions={"kotlin": "2.0.0", "agp": "8.3.0"})
    assert duplicate_version_values.check(cat) == []


def test_duplicate_version_values_silent_on_empty_versions() -> None:
    assert duplicate_version_values.check(_catalog()) == []


# ---------------------------------------------------------------------------
# catalog.inconsistent-naming
# ---------------------------------------------------------------------------


def test_inconsistent_naming_fires_when_mixing_styles() -> None:
    cat = _catalog(
        libraries=(
            _lib("core-ktx"),  # kebab-case
            _lib("composeUi"),  # camelCase
        )
    )
    findings = inconsistent_naming.check(cat)
    assert len(findings) == 1
    assert findings[0].rule_id == inconsistent_naming.ID
    assert findings[0].severity == Severity.WARNING


def test_inconsistent_naming_silent_when_all_kebab() -> None:
    cat = _catalog(libraries=(_lib("core-ktx"), _lib("compose-ui")))
    assert inconsistent_naming.check(cat) == []


def test_inconsistent_naming_silent_when_all_camel() -> None:
    cat = _catalog(libraries=(_lib("coreKtx"), _lib("composeUi")))
    assert inconsistent_naming.check(cat) == []


def test_inconsistent_naming_checks_plugins_and_bundles() -> None:
    cat = _catalog(
        plugins=(_plugin("myPlugin"),),  # camelCase
        bundles=(Bundle("my-bundle", ()),),  # kebab-case
    )
    findings = inconsistent_naming.check(cat)
    assert len(findings) == 1


# ---------------------------------------------------------------------------
# catalog.orphan-version-ref
# ---------------------------------------------------------------------------


def test_orphan_version_ref_fires_for_unreferenced_key() -> None:
    cat = _catalog(
        libraries=(_lib("core-ktx", version_ref="androidxCore"),),
        versions={"androidxCore": "1.13.0", "unused": "9.9.9"},
    )
    findings = orphan_version_ref.check(cat)
    assert len(findings) == 1
    assert findings[0].rule_id == orphan_version_ref.ID
    assert findings[0].severity == Severity.WARNING
    assert "unused" in findings[0].message


def test_orphan_version_ref_silent_when_all_keys_referenced() -> None:
    cat = _catalog(
        libraries=(_lib("core-ktx", version_ref="androidxCore"),),
        versions={"androidxCore": "1.13.0"},
    )
    assert orphan_version_ref.check(cat) == []


def test_orphan_version_ref_silent_on_empty_versions() -> None:
    assert orphan_version_ref.check(_catalog()) == []


# ---------------------------------------------------------------------------
# catalog.unresolved-version-ref
# ---------------------------------------------------------------------------


def test_unresolved_version_ref_fires_for_missing_key() -> None:
    # Construct directly, bypassing the parser's validation.
    cat = _catalog(
        libraries=(_lib("core-ktx", version_ref="missing"),),
        versions={},
    )
    findings = unresolved_version_ref.check(cat)
    assert len(findings) == 1
    assert findings[0].rule_id == unresolved_version_ref.ID
    assert findings[0].severity == Severity.ERROR
    assert "core-ktx" in findings[0].details


def test_unresolved_version_ref_fires_for_plugin_missing_key() -> None:
    cat = _catalog(
        plugins=(_plugin("agp", version_ref="missing"),),
        versions={},
    )
    assert len(unresolved_version_ref.check(cat)) == 1


def test_unresolved_version_ref_silent_when_all_keys_exist() -> None:
    cat = _catalog(
        libraries=(_lib("core-ktx", version_ref="androidxCore"),),
        versions={"androidxCore": "1.13.0"},
    )
    assert unresolved_version_ref.check(cat) == []


def test_unresolved_version_ref_silent_when_no_refs() -> None:
    cat = _catalog(libraries=(_lib("core-ktx"),))
    assert unresolved_version_ref.check(cat) == []


# ---------------------------------------------------------------------------
# catalog.duplicate-library
# ---------------------------------------------------------------------------


def test_duplicate_library_fires_for_same_coordinate() -> None:
    cat = _catalog(
        libraries=(
            _lib("alias-a", group="com.example", artifact="lib"),
            _lib("alias-b", group="com.example", artifact="lib"),
        )
    )
    findings = duplicate_library.check(cat)
    assert len(findings) == 1
    assert findings[0].rule_id == duplicate_library.ID
    assert findings[0].severity == Severity.ERROR
    assert "com.example:lib" in findings[0].message


def test_duplicate_library_emits_one_finding_per_coordinate() -> None:
    cat = _catalog(
        libraries=(
            _lib("a1", group="com.foo", artifact="bar"),
            _lib("a2", group="com.foo", artifact="bar"),
            _lib("b1", group="com.baz", artifact="qux"),
            _lib("b2", group="com.baz", artifact="qux"),
        )
    )
    assert len(duplicate_library.check(cat)) == 2


def test_duplicate_library_silent_when_all_unique() -> None:
    cat = _catalog(
        libraries=(
            _lib("core-ktx", group="androidx.core", artifact="core-ktx"),
            _lib("compose-ui", group="androidx.compose.ui", artifact="ui"),
        )
    )
    assert duplicate_library.check(cat) == []


def test_duplicate_library_silent_on_empty_catalog() -> None:
    assert duplicate_library.check(_catalog()) == []
