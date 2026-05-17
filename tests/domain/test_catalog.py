"""Unit tests for Catalog and its child entities."""

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from pathlib import Path

import pytest

from gradle_deps_monitor.domain.catalog import Bundle, Catalog, Library, Plugin
from gradle_deps_monitor.domain.report import FreezeReport
from gradle_deps_monitor.domain.rich_version import RichVersion
from gradle_deps_monitor.domain.version import MavenVersion

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _lib(
    alias: str, group: str = "com.example", artifact: str = "lib", version: str = "1.0.0"
) -> Library:
    return Library(alias=alias, group=group, artifact=artifact, version=MavenVersion(version))


def _plugin(alias: str, id: str = "com.example.plugin", version: str = "1.0.0") -> Plugin:
    return Plugin(alias=alias, id=id, version=MavenVersion(version))


def _catalog(
    *libraries: Library, plugins: tuple[Plugin, ...] = (), bundles: tuple[Bundle, ...] = ()
) -> Catalog:
    return Catalog(
        source_path=Path("/fake/libs.versions.toml"),
        libraries=libraries,
        plugins=plugins,
        bundles=bundles,
    )


# ---------------------------------------------------------------------------
# Library
# ---------------------------------------------------------------------------


def test_library_coordinate() -> None:
    lib = _lib("kotlin-stdlib", group="org.jetbrains.kotlin", artifact="kotlin-stdlib")
    assert lib.coordinate == "org.jetbrains.kotlin:kotlin-stdlib"


def test_library_notation() -> None:
    lib = _lib(
        "kotlin-stdlib", group="org.jetbrains.kotlin", artifact="kotlin-stdlib", version="2.0.0"
    )
    assert lib.notation == "org.jetbrains.kotlin:kotlin-stdlib:2.0.0"


def test_library_is_immutable() -> None:
    lib = _lib("my-lib")
    with pytest.raises(FrozenInstanceError):
        lib.alias = "other"  # type: ignore[misc]


def test_library_accepts_consistent_version_constraints() -> None:
    """RFC-0020: ``version_constraints.effective`` matches ``version``."""
    lib = Library(
        alias="kotlin-stdlib",
        group="org.jetbrains.kotlin",
        artifact="kotlin-stdlib",
        version=MavenVersion("2.0.0"),
        version_constraints=RichVersion(strictly="2.0.0"),
    )
    assert lib.version_constraints is not None
    assert lib.version_constraints.strictly == "2.0.0"


def test_library_rejects_inconsistent_version_constraints() -> None:
    """RFC-0020 invariant: divergence between ``version`` and ``effective`` is forbidden."""
    with pytest.raises(ValueError, match="must equal version"):
        Library(
            alias="kotlin-stdlib",
            group="org.jetbrains.kotlin",
            artifact="kotlin-stdlib",
            version=MavenVersion("2.0.0"),
            version_constraints=RichVersion(strictly="9.9.9"),
        )


def test_library_without_version_constraints_is_unchanged() -> None:
    """Libraries with plain-string versions keep ``version_constraints`` as ``None``."""
    lib = _lib("ordinary-lib", version="1.2.3")
    assert lib.version_constraints is None


# ---------------------------------------------------------------------------
# is_bom_candidate (issue #15 from the 2026-05 stress test menu)
# ---------------------------------------------------------------------------


def test_is_bom_candidate_recognises_bom_suffix() -> None:
    assert _lib("firebase-bom", artifact="firebase-bom").is_bom_candidate


def test_is_bom_candidate_recognises_platform_suffix() -> None:
    assert _lib("micrometer-bom", artifact="micrometer-platform").is_bom_candidate


def test_is_bom_candidate_recognises_bom_alpha_suffix() -> None:
    """RFC-0024 follow-up #15: Compose ships ``compose-bom-alpha`` as its
    alpha-line BoM. Pre-fix the suffix didn't match the ``-bom$`` regex,
    so the alpha BoM was silently treated as a plain library."""
    assert _lib("compose-bom-alpha", artifact="compose-bom-alpha").is_bom_candidate


def test_is_bom_candidate_recognises_bom_beta_suffix() -> None:
    assert _lib("some-bom-beta", artifact="some-bom-beta").is_bom_candidate


def test_is_bom_candidate_recognises_platform_rc_suffix() -> None:
    assert _lib("foo-platform-rc1", artifact="foo-platform-rc1").is_bom_candidate


def test_is_bom_candidate_negative_plain_artifact() -> None:
    assert not _lib("retrofit", artifact="retrofit").is_bom_candidate


def test_is_bom_candidate_negative_substring_only() -> None:
    """``mybomb-3.0`` contains ``-bom`` as a substring inside a longer
    word; must not match because the regex requires a hyphen boundary."""
    assert not _lib("bomb", artifact="mybomb-3.0").is_bom_candidate


# ---------------------------------------------------------------------------
# Plugin
# ---------------------------------------------------------------------------


def test_plugin_notation() -> None:
    p = Plugin(alias="agp", id="com.android.application", version=MavenVersion("8.2.0"))
    assert p.notation == "com.android.application:8.2.0"


# ---------------------------------------------------------------------------
# Bundle
# ---------------------------------------------------------------------------


def test_bundle_stores_member_aliases() -> None:
    b = Bundle(alias="compose", member_aliases=("compose-ui", "compose-runtime"))
    assert "compose-ui" in b.member_aliases
    assert len(b.member_aliases) == 2


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------


def test_catalog_library_lookup_found() -> None:
    cat = _catalog(_lib("kotlin-stdlib"), _lib("retrofit"))
    assert cat.library("retrofit") is not None
    assert cat.library("retrofit").alias == "retrofit"  # type: ignore[union-attr]


def test_catalog_library_lookup_missing() -> None:
    cat = _catalog(_lib("kotlin-stdlib"))
    assert cat.library("unknown") is None


def test_catalog_plugin_lookup_found() -> None:
    cat = _catalog(plugins=(_plugin("agp"),))
    assert cat.plugin("agp") is not None


def test_catalog_plugin_lookup_missing() -> None:
    cat = _catalog(plugins=(_plugin("agp"),))
    assert cat.plugin("kotlin") is None


def test_catalog_bundle_lookup() -> None:
    bundle = Bundle(alias="compose", member_aliases=("compose-ui",))
    cat = _catalog(bundles=(bundle,))
    assert cat.bundle("compose") is bundle
    assert cat.bundle("missing") is None


def test_catalog_counts() -> None:
    cat = _catalog(_lib("a"), _lib("b"), plugins=(_plugin("p"),))
    assert cat.library_count == 2
    assert cat.plugin_count == 1


# ---------------------------------------------------------------------------
# FreezeReport
# ---------------------------------------------------------------------------


def test_freeze_report_requires_timezone_aware_datetime() -> None:
    cat = _catalog()
    with pytest.raises(ValueError, match="timezone-aware"):
        FreezeReport(catalog=cat, generated_at=datetime(2024, 1, 1))  # naive


def test_freeze_report_defaults_to_utc_now() -> None:
    cat = _catalog()
    report = FreezeReport(catalog=cat)
    assert report.generated_at.tzinfo is not None


def test_freeze_report_holds_catalog() -> None:
    cat = _catalog(_lib("retrofit"))
    report = FreezeReport(catalog=cat, generated_at=datetime(2024, 6, 1, tzinfo=UTC))
    assert report.catalog is cat
