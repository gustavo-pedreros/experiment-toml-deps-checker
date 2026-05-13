"""Parser tests for Gradle rich versions (RFC-0020).

Before this RFC, ``_resolve_version`` raised ``CatalogParseError`` on
any version table without a ``ref`` key. These tests verify that:

1. Each of the four rich-version keys parses without crashing.
2. The effective version is resolved per Gradle precedence.
3. The ``RichVersion`` metadata is preserved on ``Library``.
4. A production-style catalog mixing rich, plain, and ref-based
   versions in the same file parses end-to-end.

Plugin-side rich-version metadata is parsed (no crash) but not yet
surfaced; that is a Phase 3 follow-up of RFC-0020.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from gradle_deps_monitor.application.ports.catalog_parser import CatalogParseError
from gradle_deps_monitor.infrastructure.parsing.toml_catalog_parser import TomlCatalogParser

PARSER = TomlCatalogParser()

# Project-level path to the production-style fixture catalog.
FIXTURE_PATH = (
    Path(__file__).parent.parent.parent / "fixtures" / "rich_versions" / "libs.versions.toml"
)


def _write(path: Path, content: str) -> Path:
    toml = path / "libs.versions.toml"
    toml.write_text(content, encoding="utf-8")
    return toml


# ---------------------------------------------------------------------------
# Regression: the original crash no longer happens
# ---------------------------------------------------------------------------


def test_strictly_block_does_not_crash(tmp_path: Path) -> None:
    """Reproduces the pre-RFC crash on a minimal catalog."""
    PARSER.parse(
        _write(
            tmp_path,
            """\
[libraries]
kotlin-stdlib = { module = "org.jetbrains.kotlin:kotlin-stdlib", version = { strictly = "2.0.0" } }
""",
        )
    )


def test_reject_only_does_not_crash(tmp_path: Path) -> None:
    """Reject-only libraries used to crash the parser; they no longer do."""
    PARSER.parse(
        _write(
            tmp_path,
            """\
[libraries]
coil = { module = "io.coil-kt:coil-compose", version = { reject = ["2.5.0"] } }
""",
        )
    )


# ---------------------------------------------------------------------------
# Effective version follows Gradle precedence
# ---------------------------------------------------------------------------


def test_strictly_resolves_to_effective(tmp_path: Path) -> None:
    cat = PARSER.parse(
        _write(
            tmp_path,
            """\
[libraries]
kotlin = { module = "org.jetbrains.kotlin:kotlin-stdlib", version = { strictly = "2.0.0" } }
""",
        )
    )
    lib = cat.library("kotlin")
    assert lib is not None
    assert str(lib.version) == "2.0.0"
    assert lib.version_constraints is not None
    assert lib.version_constraints.strictly == "2.0.0"


def test_require_resolves_to_effective(tmp_path: Path) -> None:
    cat = PARSER.parse(
        _write(
            tmp_path,
            """\
[libraries]
agp = { module = "com.android.tools.build:gradle", version = { require = "8.3.0" } }
""",
        )
    )
    lib = cat.library("agp")
    assert lib is not None
    assert str(lib.version) == "8.3.0"


def test_prefer_resolves_to_effective(tmp_path: Path) -> None:
    cat = PARSER.parse(
        _write(
            tmp_path,
            """\
[libraries]
hilt = { module = "com.google.dagger:hilt-android", version = { prefer = "2.51.1" } }
""",
        )
    )
    lib = cat.library("hilt")
    assert lib is not None
    assert str(lib.version) == "2.51.1"


def test_strictly_wins_over_require_and_prefer(tmp_path: Path) -> None:
    cat = PARSER.parse(
        _write(
            tmp_path,
            """\
[libraries]
lib = { module = "com.example:lib", version = { strictly = "1.0.0", require = "2.0.0", prefer = "3.0.0" } }
""",
        )
    )
    lib = cat.library("lib")
    assert lib is not None
    assert str(lib.version) == "1.0.0"


def test_reject_only_has_empty_effective_version(tmp_path: Path) -> None:
    """No positive pin → ``version`` is the empty-string sentinel."""
    cat = PARSER.parse(
        _write(
            tmp_path,
            """\
[libraries]
coil = { module = "io.coil-kt:coil-compose", version = { reject = ["2.5.0"] } }
""",
        )
    )
    lib = cat.library("coil")
    assert lib is not None
    assert lib.version.raw == ""
    assert lib.version_constraints is not None
    assert lib.version_constraints.reject == ("2.5.0",)
    assert lib.version_constraints.is_reject_only


# ---------------------------------------------------------------------------
# Plain-string and ref versions remain unaffected (no constraints field)
# ---------------------------------------------------------------------------


def test_plain_string_version_has_no_constraints(tmp_path: Path) -> None:
    cat = PARSER.parse(
        _write(
            tmp_path,
            """\
[libraries]
okhttp = { module = "com.squareup.okhttp3:okhttp", version = "4.12.0" }
""",
        )
    )
    lib = cat.library("okhttp")
    assert lib is not None
    assert lib.version_constraints is None


def test_version_ref_has_no_constraints(tmp_path: Path) -> None:
    cat = PARSER.parse(
        _write(
            tmp_path,
            """\
[versions]
kotlin = "2.0.0"
[libraries]
stdlib = { module = "org.jetbrains.kotlin:kotlin-stdlib", version.ref = "kotlin" }
""",
        )
    )
    lib = cat.library("stdlib")
    assert lib is not None
    assert lib.version_ref == "kotlin"
    assert lib.version_constraints is None


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


def test_combining_ref_with_rich_keys_is_rejected(tmp_path: Path) -> None:
    """Phase 1 keeps the two forms strictly disjoint."""
    with pytest.raises(CatalogParseError, match="combining 'ref' with rich-version keys"):
        PARSER.parse(
            _write(
                tmp_path,
                """\
[versions]
kotlin = "2.0.0"
[libraries]
mix = { module = "com.example:lib", version = { ref = "kotlin", strictly = "2.0.0" } }
""",
            )
        )


def test_empty_version_table_is_rejected(tmp_path: Path) -> None:
    """A table without either ``ref`` or rich keys is a user error."""
    with pytest.raises(CatalogParseError, match="version table has no 'ref' key and no rich"):
        PARSER.parse(
            _write(
                tmp_path,
                """\
[libraries]
broken = { module = "com.example:lib", version = {} }
""",
            )
        )


def test_strictly_must_be_string(tmp_path: Path) -> None:
    with pytest.raises(CatalogParseError, match="rich-version key 'strictly' must be a string"):
        PARSER.parse(
            _write(
                tmp_path,
                """\
[libraries]
lib = { module = "com.example:lib", version = { strictly = 123 } }
""",
            )
        )


def test_reject_must_be_list_of_strings(tmp_path: Path) -> None:
    with pytest.raises(CatalogParseError, match="rich-version key 'reject' must be a list"):
        PARSER.parse(
            _write(
                tmp_path,
                """\
[libraries]
lib = { module = "com.example:lib", version = { reject = "1.0.0" } }
""",
            )
        )


# ---------------------------------------------------------------------------
# Plugins: the crash is fixed even when metadata is dropped
# ---------------------------------------------------------------------------


def test_plugin_with_rich_version_does_not_crash(tmp_path: Path) -> None:
    """Plugin rich versions parse without crashing (metadata is dropped for now)."""
    cat = PARSER.parse(
        _write(
            tmp_path,
            """\
[plugins]
agp = { id = "com.android.application", version = { require = "8.3.0" } }
""",
        )
    )
    p = cat.plugin("agp")
    assert p is not None
    assert str(p.version) == "8.3.0"


# ---------------------------------------------------------------------------
# End-to-end against the production-style fixture
# ---------------------------------------------------------------------------


def test_production_style_fixture_parses() -> None:
    """The tracer's headline regression: a realistic toolchain catalog parses."""
    cat = PARSER.parse(FIXTURE_PATH)
    # Spot-check each rich-version pattern in the fixture.
    kotlin = cat.library("kotlin-stdlib")
    assert kotlin is not None and kotlin.version_constraints is not None
    assert kotlin.version_constraints.strictly == "2.0.0"

    ksp = cat.library("ksp-api")
    assert ksp is not None and ksp.version_constraints is not None
    assert ksp.version_constraints.strictly == "2.0.0-1.0.21"

    agp = cat.library("agp-gradle")
    assert agp is not None and agp.version_constraints is not None
    assert agp.version_constraints.require == "8.3.0"

    hilt = cat.library("hilt-android")
    assert hilt is not None and hilt.version_constraints is not None
    assert hilt.version_constraints.prefer == "2.51.1"

    coil = cat.library("coil-compose")
    assert coil is not None and coil.version_constraints is not None
    assert coil.version_constraints.reject == ("2.5.0", "2.5.0-rc1")
    assert coil.version.raw == ""

    # The plain-string + ref-based library in the same file should be
    # unaffected: no version_constraints attached.
    compose_ui = cat.library("compose-ui")
    assert compose_ui is not None
    assert compose_ui.version_constraints is None
    assert str(compose_ui.version) == "1.6.4"
