"""Tests for ToolchainCompatibilityChecker."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from gradle_deps_monitor.domain.catalog import Catalog
from gradle_deps_monitor.domain.toolchain import ToolchainSeverity
from gradle_deps_monitor.infrastructure.checkers.toolchain_compatibility_checker import (
    ToolchainCompatibilityChecker,
    _find_gradle_version,
    _find_toolchain_versions,
    _normalize_key,
    _version_tuple,
)
from gradle_deps_monitor.infrastructure.parsing.toml_catalog_parser import TomlCatalogParser

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_catalog(tmp_path: Path, toml_content: str) -> Catalog:
    """Write a TOML file and parse it with the real ``TomlCatalogParser``.

    Returns a real :class:`Catalog`. RFC-0020 PR #2 made the toolchain
    checker a pure consumer of the domain model (no TOML re-parse), so
    the tests now exercise the same path as production.
    """
    toml_file = tmp_path / "libs.versions.toml"
    toml_file.write_text(textwrap.dedent(toml_content), encoding="utf-8")
    return TomlCatalogParser().parse(toml_file)


def _catalog_with_versions(tmp_path: Path, versions: dict[str, str]) -> Catalog:
    """Build a Catalog with an arbitrary versions map, no TOML on disk.

    Useful for unit tests of helpers that only need ``Catalog.versions``
    and a stable ``source_path``.
    """
    return Catalog(
        source_path=tmp_path / "libs.versions.toml",
        libraries=(),
        plugins=(),
        bundles=(),
        versions=dict(versions),
    )


def _make_wrapper(tmp_path: Path, gradle_version: str) -> None:
    """Write a minimal gradle-wrapper.properties under tmp_path/wrapper/."""
    wrapper_dir = tmp_path / "wrapper"
    wrapper_dir.mkdir(parents=True, exist_ok=True)
    props = wrapper_dir / "gradle-wrapper.properties"
    props.write_text(
        f"distributionUrl=https\\://services.gradle.org/distributions/"
        f"gradle-{gradle_version}-bin.zip\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# _normalize_key
# ---------------------------------------------------------------------------


class TestNormalizeKey:
    def test_lowercase(self) -> None:
        assert _normalize_key("Kotlin") == "kotlin"

    def test_removes_hyphens(self) -> None:
        assert _normalize_key("kotlin-version") == "kotlinversion"

    def test_removes_underscores(self) -> None:
        assert _normalize_key("ksp_version") == "kspversion"

    def test_camel_case_preserved(self) -> None:
        # CamelCase letters are lowercased but not stripped
        assert _normalize_key("kotlinVersion") == "kotlinversion"

    def test_compose_compiler(self) -> None:
        assert _normalize_key("composeCompiler") == "composecompiler"

    def test_agp_variants(self) -> None:
        assert _normalize_key("android-gradle-plugin") == "androidgradleplugin"
        assert _normalize_key("agp") == "agp"


# ---------------------------------------------------------------------------
# _version_tuple
# ---------------------------------------------------------------------------


class TestVersionTuple:
    def test_two_part(self) -> None:
        assert _version_tuple("8.11") == (8, 11)

    def test_three_part(self) -> None:
        assert _version_tuple("8.11.1") == (8, 11, 1)

    def test_single(self) -> None:
        assert _version_tuple("8") == (8,)

    def test_invalid_returns_zero(self) -> None:
        assert _version_tuple("bad") == (0,)


# ---------------------------------------------------------------------------
# _find_toolchain_versions
# ---------------------------------------------------------------------------


class TestFindToolchainVersions:
    def test_detects_kotlin(self, tmp_path: Path) -> None:
        cat = _make_catalog(
            tmp_path,
            """\
            [versions]
            kotlin = "2.1.10"
            """,
        )
        v = _find_toolchain_versions(cat)
        assert v["kotlin"] == "2.1.10"

    def test_detects_kotlin_camel_case(self, tmp_path: Path) -> None:
        cat = _make_catalog(
            tmp_path,
            """\
            [versions]
            kotlinVersion = "1.9.22"
            """,
        )
        v = _find_toolchain_versions(cat)
        assert v["kotlin"] == "1.9.22"

    def test_detects_agp(self, tmp_path: Path) -> None:
        cat = _make_catalog(
            tmp_path,
            """\
            [versions]
            agp = "8.5.0"
            """,
        )
        v = _find_toolchain_versions(cat)
        assert v["agp"] == "8.5.0"

    def test_detects_ksp(self, tmp_path: Path) -> None:
        cat = _make_catalog(
            tmp_path,
            """\
            [versions]
            ksp = "2.1.10-1.0.29"
            """,
        )
        v = _find_toolchain_versions(cat)
        assert v["ksp"] == "2.1.10-1.0.29"

    def test_detects_compose_compiler(self, tmp_path: Path) -> None:
        cat = _make_catalog(
            tmp_path,
            """\
            [versions]
            composeCompiler = "1.5.8"
            """,
        )
        v = _find_toolchain_versions(cat)
        assert v["compose_compiler"] == "1.5.8"

    def test_empty_versions_returns_empty(self, tmp_path: Path) -> None:
        """An empty catalog versions map yields no toolchain entries.

        RFC-0020 PR #2 replaced the previous "ignore non-string values"
        path: the parser now rejects unsupported types in ``[versions]``
        at parse time (matching Gradle's own constraint). The checker
        sees only valid string entries.
        """
        cat = _catalog_with_versions(tmp_path, {})
        assert _find_toolchain_versions(cat) == {}

    def test_detects_kotlin_pinned_with_strictly(self, tmp_path: Path) -> None:
        """RFC-0020 §2: ``[versions]`` rich blocks are flattened to the effective string."""
        cat = _make_catalog(
            tmp_path,
            """\
            [versions]
            kotlin = { strictly = "2.0.21" }
            """,
        )
        v = _find_toolchain_versions(cat)
        assert v["kotlin"] == "2.0.21"

    def test_skips_reject_only_entries(self, tmp_path: Path) -> None:
        """Reject-only rich blocks have no positive pin → checker skips them."""
        cat = _make_catalog(
            tmp_path,
            """\
            [versions]
            kotlin = { reject = ["2.0.0"] }
            """,
        )
        v = _find_toolchain_versions(cat)
        assert "kotlin" not in v

    def test_first_match_wins(self, tmp_path: Path) -> None:
        """When two keys normalize to the same token the first one wins."""
        cat = _make_catalog(
            tmp_path,
            """\
            [versions]
            kotlin = "2.1.0"
            kotlinVersion = "1.9.22"
            """,
        )
        v = _find_toolchain_versions(cat)
        assert v["kotlin"] == "2.1.0"


# ---------------------------------------------------------------------------
# _find_gradle_version
# ---------------------------------------------------------------------------


class TestFindGradleVersion:
    def test_reads_bin_zip(self, tmp_path: Path) -> None:
        _make_wrapper(tmp_path, "8.11")
        cat = _catalog_with_versions(tmp_path, {})
        assert _find_gradle_version(cat) == "8.11"

    def test_reads_three_part_version(self, tmp_path: Path) -> None:
        _make_wrapper(tmp_path, "8.11.1")
        cat = _catalog_with_versions(tmp_path, {})
        assert _find_gradle_version(cat) == "8.11.1"

    def test_returns_none_when_missing(self, tmp_path: Path) -> None:
        cat = _catalog_with_versions(tmp_path, {})
        assert _find_gradle_version(cat) is None


# ---------------------------------------------------------------------------
# ToolchainCompatibilityChecker — TOOL-KC-001 (Kotlin ↔ Compose)
# ---------------------------------------------------------------------------


class TestKotlinComposeCheck:
    @pytest.fixture
    def checker(self) -> ToolchainCompatibilityChecker:
        return ToolchainCompatibilityChecker()

    def test_ok_kotlin_1x(self, checker: ToolchainCompatibilityChecker, tmp_path: Path) -> None:
        cat = _make_catalog(
            tmp_path,
            """\
            [versions]
            kotlin = "1.9.22"
            composeCompiler = "1.5.8"
            """,
        )
        findings = checker.check(cat)
        kc = [f for f in findings if f.rule_id == "TOOL-KC-001"]
        assert not kc

    def test_error_kotlin_1x_mismatch(
        self, checker: ToolchainCompatibilityChecker, tmp_path: Path
    ) -> None:
        cat = _make_catalog(
            tmp_path,
            """\
            [versions]
            kotlin = "1.9.22"
            composeCompiler = "1.5.6"
            """,
        )
        findings = checker.check(cat)
        kc = [f for f in findings if f.rule_id == "TOOL-KC-001"]
        assert len(kc) == 1
        assert kc[0].severity == ToolchainSeverity.ERROR
        assert "1.5.8" in kc[0].message

    def test_ok_kotlin_2x_matching(
        self, checker: ToolchainCompatibilityChecker, tmp_path: Path
    ) -> None:
        cat = _make_catalog(
            tmp_path,
            """\
            [versions]
            kotlin = "2.1.10"
            composeCompiler = "2.1.10"
            """,
        )
        findings = checker.check(cat)
        kc = [f for f in findings if f.rule_id == "TOOL-KC-001"]
        assert not kc

    def test_error_kotlin_2x_mismatch(
        self, checker: ToolchainCompatibilityChecker, tmp_path: Path
    ) -> None:
        cat = _make_catalog(
            tmp_path,
            """\
            [versions]
            kotlin = "2.1.10"
            composeCompiler = "2.1.0"
            """,
        )
        findings = checker.check(cat)
        kc = [f for f in findings if f.rule_id == "TOOL-KC-001"]
        assert len(kc) == 1
        assert kc[0].severity == ToolchainSeverity.ERROR

    def test_warning_kotlin_1x_unknown(
        self, checker: ToolchainCompatibilityChecker, tmp_path: Path
    ) -> None:
        cat = _make_catalog(
            tmp_path,
            """\
            [versions]
            kotlin = "1.6.99"
            composeCompiler = "1.3.0"
            """,
        )
        findings = checker.check(cat)
        kc = [f for f in findings if f.rule_id == "TOOL-KC-001"]
        assert len(kc) == 1
        assert kc[0].severity == ToolchainSeverity.WARNING

    def test_no_finding_when_compose_absent(
        self, checker: ToolchainCompatibilityChecker, tmp_path: Path
    ) -> None:
        cat = _make_catalog(
            tmp_path,
            """\
            [versions]
            kotlin = "2.1.10"
            """,
        )
        findings = checker.check(cat)
        kc = [f for f in findings if f.rule_id == "TOOL-KC-001"]
        assert not kc

    def test_no_finding_when_kotlin_absent(
        self, checker: ToolchainCompatibilityChecker, tmp_path: Path
    ) -> None:
        cat = _make_catalog(
            tmp_path,
            """\
            [versions]
            composeCompiler = "1.5.8"
            """,
        )
        findings = checker.check(cat)
        kc = [f for f in findings if f.rule_id == "TOOL-KC-001"]
        assert not kc


# ---------------------------------------------------------------------------
# ToolchainCompatibilityChecker — TOOL-KSP-001 (Kotlin ↔ KSP)
# ---------------------------------------------------------------------------


class TestKotlinKspCheck:
    @pytest.fixture
    def checker(self) -> ToolchainCompatibilityChecker:
        return ToolchainCompatibilityChecker()

    def test_ok_matching_prefix(
        self, checker: ToolchainCompatibilityChecker, tmp_path: Path
    ) -> None:
        cat = _make_catalog(
            tmp_path,
            """\
            [versions]
            kotlin = "2.1.10"
            ksp = "2.1.10-1.0.29"
            """,
        )
        findings = checker.check(cat)
        ksp = [f for f in findings if f.rule_id == "TOOL-KSP-001"]
        assert not ksp

    def test_error_mismatched_prefix(
        self, checker: ToolchainCompatibilityChecker, tmp_path: Path
    ) -> None:
        cat = _make_catalog(
            tmp_path,
            """\
            [versions]
            kotlin = "2.1.10"
            ksp = "2.1.0-1.0.29"
            """,
        )
        findings = checker.check(cat)
        ksp = [f for f in findings if f.rule_id == "TOOL-KSP-001"]
        assert len(ksp) == 1
        assert ksp[0].severity == ToolchainSeverity.ERROR
        assert "2.1.10" in ksp[0].message

    def test_error_includes_recommendation(
        self, checker: ToolchainCompatibilityChecker, tmp_path: Path
    ) -> None:
        cat = _make_catalog(
            tmp_path,
            """\
            [versions]
            kotlin = "2.1.10"
            ksp = "2.1.0-1.0.29"
            """,
        )
        findings = checker.check(cat)
        ksp = [f for f in findings if f.rule_id == "TOOL-KSP-001"]
        assert ksp[0].recommendation != ""
        assert "2.1.10-1.0.29" in ksp[0].recommendation

    def test_no_finding_when_ksp_absent(
        self, checker: ToolchainCompatibilityChecker, tmp_path: Path
    ) -> None:
        cat = _make_catalog(
            tmp_path,
            """\
            [versions]
            kotlin = "2.1.10"
            """,
        )
        findings = checker.check(cat)
        assert not [f for f in findings if f.rule_id == "TOOL-KSP-001"]


# ---------------------------------------------------------------------------
# ToolchainCompatibilityChecker — TOOL-AGP-001 (AGP ↔ Gradle)
# ---------------------------------------------------------------------------


class TestAgpGradleCheck:
    @pytest.fixture
    def checker(self) -> ToolchainCompatibilityChecker:
        return ToolchainCompatibilityChecker()

    def test_ok_sufficient_gradle(
        self, checker: ToolchainCompatibilityChecker, tmp_path: Path
    ) -> None:
        cat = _make_catalog(
            tmp_path,
            """\
            [versions]
            agp = "8.5.0"
            """,
        )
        _make_wrapper(tmp_path, "8.7")
        findings = checker.check(cat)
        agp = [f for f in findings if f.rule_id == "TOOL-AGP-001"]
        assert not agp

    def test_error_insufficient_gradle(
        self, checker: ToolchainCompatibilityChecker, tmp_path: Path
    ) -> None:
        cat = _make_catalog(
            tmp_path,
            """\
            [versions]
            agp = "8.9.0"
            """,
        )
        _make_wrapper(tmp_path, "8.9")
        findings = checker.check(cat)
        agp = [f for f in findings if f.rule_id == "TOOL-AGP-001"]
        assert len(agp) == 1
        assert agp[0].severity == ToolchainSeverity.ERROR
        assert "8.11" in agp[0].message

    def test_error_contains_recommendation(
        self, checker: ToolchainCompatibilityChecker, tmp_path: Path
    ) -> None:
        cat = _make_catalog(
            tmp_path,
            """\
            [versions]
            agp = "8.8.0"
            """,
        )
        _make_wrapper(tmp_path, "8.9")
        findings = checker.check(cat)
        agp = [f for f in findings if f.rule_id == "TOOL-AGP-001"]
        assert agp[0].recommendation != ""

    def test_no_finding_when_wrapper_missing(
        self, checker: ToolchainCompatibilityChecker, tmp_path: Path
    ) -> None:
        cat = _make_catalog(
            tmp_path,
            """\
            [versions]
            agp = "8.9.0"
            """,
        )
        findings = checker.check(cat)
        agp = [f for f in findings if f.rule_id == "TOOL-AGP-001"]
        assert not agp

    def test_no_finding_when_agp_absent(
        self, checker: ToolchainCompatibilityChecker, tmp_path: Path
    ) -> None:
        cat = _make_catalog(
            tmp_path,
            """\
            [versions]
            kotlin = "2.1.10"
            """,
        )
        _make_wrapper(tmp_path, "8.11")
        findings = checker.check(cat)
        assert not [f for f in findings if f.rule_id == "TOOL-AGP-001"]

    def test_agp_below_all_matrix_entries_skipped(
        self, checker: ToolchainCompatibilityChecker, tmp_path: Path
    ) -> None:
        """AGP version older than the lowest matrix entry → no applicable rule."""
        cat = _make_catalog(
            tmp_path,
            """\
            [versions]
            agp = "6.5.0"
            """,
        )
        _make_wrapper(tmp_path, "6.5")
        findings = checker.check(cat)
        assert not [f for f in findings if f.rule_id == "TOOL-AGP-001"]

    def test_exact_min_gradle_is_sufficient(
        self, checker: ToolchainCompatibilityChecker, tmp_path: Path
    ) -> None:
        """Gradle version equal to min_gradle must not produce a finding."""
        cat = _make_catalog(
            tmp_path,
            """\
            [versions]
            agp = "8.9.0"
            """,
        )
        _make_wrapper(tmp_path, "8.11")
        findings = checker.check(cat)
        agp = [f for f in findings if f.rule_id == "TOOL-AGP-001"]
        assert not agp


# ---------------------------------------------------------------------------
# Empty catalog — no findings at all
# ---------------------------------------------------------------------------


class TestEmptyCatalog:
    def test_no_findings_for_empty_versions(self, tmp_path: Path) -> None:
        cat = _make_catalog(
            tmp_path,
            """\
            [versions]

            [libraries]
            """,
        )
        checker = ToolchainCompatibilityChecker()
        findings = checker.check(cat)
        assert findings == ()
