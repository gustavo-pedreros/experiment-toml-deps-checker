"""Unit tests for GradleModuleScanner.

All tests use ``tmp_path`` (pytest fixture) — no network, no real Gradle projects.
"""

from __future__ import annotations

from pathlib import Path

from gradle_deps_monitor.domain.catalog import Catalog, Library
from gradle_deps_monitor.domain.version import MavenVersion
from gradle_deps_monitor.infrastructure.scanners.gradle_module_scanner import (
    GradleModuleScanner,
    _alias_to_accessor,
    _find_project_root,
    _parse_module_paths,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _catalog(*aliases: str) -> Catalog:
    """Build a minimal Catalog with one library per alias."""
    libs = tuple(
        Library(
            alias=alias,
            group="com.example",
            artifact=alias,
            version=MavenVersion("1.0.0"),
        )
        for alias in aliases
    )
    return Catalog(
        source_path=Path("/fake/gradle/libs.versions.toml"),
        libraries=libs,
        plugins=(),
        bundles=(),
    )


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


class TestAliasToAccessor:
    def test_simple(self) -> None:
        assert _alias_to_accessor("retrofit") == "retrofit"

    def test_dashes_become_dots(self) -> None:
        assert _alias_to_accessor("squareup-retrofit") == "squareup.retrofit"

    def test_multi_segment(self) -> None:
        assert _alias_to_accessor("androidx-core-ktx") == "androidx.core.ktx"

    def test_lowercased(self) -> None:
        assert _alias_to_accessor("OkHttp") == "okhttp"


class TestFindProjectRoot:
    def test_finds_kts_in_same_dir(self, tmp_path: Path) -> None:
        (tmp_path / "settings.gradle.kts").write_text("")
        gradle_dir = tmp_path / "gradle"
        gradle_dir.mkdir()
        result = _find_project_root(gradle_dir)
        assert result == tmp_path

    def test_finds_groovy_in_same_dir(self, tmp_path: Path) -> None:
        (tmp_path / "settings.gradle").write_text("")
        gradle_dir = tmp_path / "gradle"
        gradle_dir.mkdir()
        result = _find_project_root(gradle_dir)
        assert result == tmp_path

    def test_finds_when_catalog_is_directly_in_root(self, tmp_path: Path) -> None:
        (tmp_path / "settings.gradle.kts").write_text("")
        result = _find_project_root(tmp_path)
        assert result == tmp_path

    def test_returns_none_when_not_found(self, tmp_path: Path) -> None:
        deep = tmp_path / "a" / "b" / "c" / "d" / "e"
        deep.mkdir(parents=True)
        assert _find_project_root(deep) is None

    def test_kts_preferred_over_groovy(self, tmp_path: Path) -> None:
        (tmp_path / "settings.gradle.kts").write_text("")
        (tmp_path / "settings.gradle").write_text("")
        result = _find_project_root(tmp_path)
        assert result == tmp_path


class TestParseModulePaths:
    def test_kts_single(self) -> None:
        assert _parse_module_paths('include(":app")') == [":app"]

    def test_kts_multi_arg(self) -> None:
        paths = _parse_module_paths('include(":app", ":feature:auth")')
        assert ":app" in paths
        assert ":feature:auth" in paths

    def test_groovy_style(self) -> None:
        paths = _parse_module_paths("include ':app'")
        assert ":app" in paths

    def test_groovy_multi_arg(self) -> None:
        paths = _parse_module_paths("include ':app', ':feature:payments'")
        assert ":app" in paths
        assert ":feature:payments" in paths

    def test_ignores_comment_lines(self) -> None:
        text = "// include(':disabled')\ninclude(':app')"
        assert _parse_module_paths(text) == [":app"]

    def test_bare_name_without_colon(self) -> None:
        paths = _parse_module_paths('include("app")')
        assert ":app" in paths

    def test_empty(self) -> None:
        assert _parse_module_paths("") == []

    def test_multiline_settings(self) -> None:
        settings = """
rootProject.name = "myapp"
include(":app")
include(":feature:auth")
include(":network:core")
"""
        paths = _parse_module_paths(settings)
        assert ":app" in paths
        assert ":feature:auth" in paths
        assert ":network:core" in paths


# ---------------------------------------------------------------------------
# GradleModuleScanner integration
# ---------------------------------------------------------------------------


class TestGradleModuleScannerNoSettings:
    def test_returns_none_when_no_settings(self, tmp_path: Path) -> None:
        catalog_dir = tmp_path / "gradle"
        catalog_dir.mkdir()
        scanner = GradleModuleScanner()
        result = scanner.scan(catalog_dir, _catalog("retrofit"))
        assert result is None

    def test_returns_none_when_no_modules(self, tmp_path: Path) -> None:
        _write(tmp_path / "settings.gradle.kts", 'rootProject.name = "myapp"')
        scanner = GradleModuleScanner()
        result = scanner.scan(tmp_path, _catalog("retrofit"))
        assert result is None


class TestGradleModuleScannerBasic:
    def _setup(self, tmp_path: Path) -> Path:
        """Create a minimal 2-module project and return catalog_dir."""
        _write(
            tmp_path / "settings.gradle.kts",
            'include(":app")\ninclude(":feature:auth")',
        )
        _write(
            tmp_path / "app" / "build.gradle.kts",
            "dependencies {\n    implementation(libs.retrofit)\n}",
        )
        _write(
            tmp_path / "feature" / "auth" / "build.gradle.kts",
            "dependencies {\n    implementation(libs.retrofit)\n    api(libs.okhttp)\n}",
        )
        catalog_dir = tmp_path / "gradle"
        catalog_dir.mkdir()
        return catalog_dir

    def test_returns_map(self, tmp_path: Path) -> None:
        catalog_dir = self._setup(tmp_path)
        result = GradleModuleScanner().scan(catalog_dir, _catalog("retrofit", "okhttp"))
        assert result is not None

    def test_modules_scanned(self, tmp_path: Path) -> None:
        catalog_dir = self._setup(tmp_path)
        result = GradleModuleScanner().scan(catalog_dir, _catalog("retrofit", "okhttp"))
        assert result is not None
        assert result.modules_scanned == 2

    def test_impl_usage(self, tmp_path: Path) -> None:
        catalog_dir = self._setup(tmp_path)
        result = GradleModuleScanner().scan(catalog_dir, _catalog("retrofit", "okhttp"))
        assert result is not None
        usages = {u.alias: u for u in result.library_usages}
        assert ":app" in usages["retrofit"].implementation_modules
        assert ":feature:auth" in usages["retrofit"].implementation_modules

    def test_api_usage(self, tmp_path: Path) -> None:
        catalog_dir = self._setup(tmp_path)
        result = GradleModuleScanner().scan(catalog_dir, _catalog("retrofit", "okhttp"))
        assert result is not None
        usages = {u.alias: u for u in result.library_usages}
        assert ":feature:auth" in usages["okhttp"].api_modules

    def test_unused_library_zero_count(self, tmp_path: Path) -> None:
        catalog_dir = self._setup(tmp_path)
        result = GradleModuleScanner().scan(catalog_dir, _catalog("retrofit", "okhttp", "junit"))
        assert result is not None
        usages = {u.alias: u for u in result.library_usages}
        assert usages["junit"].total_count == 0

    def test_libraries_in_use_excludes_zero(self, tmp_path: Path) -> None:
        catalog_dir = self._setup(tmp_path)
        result = GradleModuleScanner().scan(catalog_dir, _catalog("retrofit", "okhttp", "junit"))
        assert result is not None
        in_use_aliases = {u.alias for u in result.libraries_in_use()}
        assert "junit" not in in_use_aliases

    def test_module_summaries(self, tmp_path: Path) -> None:
        catalog_dir = self._setup(tmp_path)
        result = GradleModuleScanner().scan(catalog_dir, _catalog("retrofit", "okhttp"))
        assert result is not None
        counts = {s.module_path: s.direct_dep_count for s in result.module_summaries}
        # :app has 1 direct dep (retrofit impl)
        assert counts[":app"] == 1
        # :feature:auth has 2 direct deps (retrofit impl + okhttp api)
        assert counts[":feature:auth"] == 2

    def test_top_modules(self, tmp_path: Path) -> None:
        catalog_dir = self._setup(tmp_path)
        result = GradleModuleScanner().scan(catalog_dir, _catalog("retrofit", "okhttp"))
        assert result is not None
        top = result.top_modules(1)
        assert top[0].module_path == ":feature:auth"


class TestGradleModuleScannerConfigurations:
    def test_test_implementation(self, tmp_path: Path) -> None:
        _write(tmp_path / "settings.gradle.kts", 'include(":app")')
        _write(
            tmp_path / "app" / "build.gradle.kts",
            "dependencies {\n    testImplementation(libs.junit)\n}",
        )
        result = GradleModuleScanner().scan(tmp_path, _catalog("junit"))
        assert result is not None
        usages = {u.alias: u for u in result.library_usages}
        assert ":app" in usages["junit"].test_modules
        assert usages["junit"].direct_count == 0

    def test_android_test_implementation(self, tmp_path: Path) -> None:
        _write(tmp_path / "settings.gradle.kts", 'include(":app")')
        _write(
            tmp_path / "app" / "build.gradle.kts",
            "dependencies {\n    androidTestImplementation(libs.espresso)\n}",
        )
        result = GradleModuleScanner().scan(tmp_path, _catalog("espresso"))
        assert result is not None
        usages = {u.alias: u for u in result.library_usages}
        assert ":app" in usages["espresso"].test_modules

    def test_ksp_config(self, tmp_path: Path) -> None:
        _write(tmp_path / "settings.gradle.kts", 'include(":app")')
        _write(
            tmp_path / "app" / "build.gradle.kts",
            "dependencies {\n    ksp(libs.hilt)\n}",
        )
        result = GradleModuleScanner().scan(tmp_path, _catalog("hilt"))
        assert result is not None
        usages = {u.alias: u for u in result.library_usages}
        assert ":app" in usages["hilt"].implementation_modules

    def test_groovy_no_parens(self, tmp_path: Path) -> None:
        _write(tmp_path / "settings.gradle", "include ':app'")
        _write(
            tmp_path / "app" / "build.gradle",
            "dependencies {\n    implementation libs.retrofit\n}",
        )
        result = GradleModuleScanner().scan(tmp_path, _catalog("retrofit"))
        assert result is not None
        usages = {u.alias: u for u in result.library_usages}
        assert ":app" in usages["retrofit"].implementation_modules

    def test_no_duplicate_modules_in_list(self, tmp_path: Path) -> None:
        """Same lib declared twice in the same build file — should be deduplicated."""
        _write(tmp_path / "settings.gradle.kts", 'include(":app")')
        _write(
            tmp_path / "app" / "build.gradle.kts",
            "dependencies {\n"
            "    implementation(libs.retrofit)\n"
            "    implementation(libs.retrofit)\n"
            "}",
        )
        result = GradleModuleScanner().scan(tmp_path, _catalog("retrofit"))
        assert result is not None
        usages = {u.alias: u for u in result.library_usages}
        assert usages["retrofit"].implementation_modules.count(":app") == 1


class TestGradleModuleScannerEdgeCases:
    def test_missing_build_file_skipped(self, tmp_path: Path) -> None:
        _write(tmp_path / "settings.gradle.kts", 'include(":app")\ninclude(":ghost")')
        _write(
            tmp_path / "app" / "build.gradle.kts",
            "dependencies { implementation(libs.retrofit) }",
        )
        # :ghost has no build file
        result = GradleModuleScanner().scan(tmp_path, _catalog("retrofit"))
        assert result is not None
        assert result.modules_scanned == 1  # only :app was scanned

    def test_unknown_accessor_ignored(self, tmp_path: Path) -> None:
        _write(tmp_path / "settings.gradle.kts", 'include(":app")')
        _write(
            tmp_path / "app" / "build.gradle.kts",
            "dependencies { implementation(libs.notInCatalog) }",
        )
        result = GradleModuleScanner().scan(tmp_path, _catalog("retrofit"))
        assert result is not None
        usages = {u.alias: u for u in result.library_usages}
        assert usages["retrofit"].total_count == 0

    def test_multi_segment_alias(self, tmp_path: Path) -> None:
        _write(tmp_path / "settings.gradle.kts", 'include(":app")')
        _write(
            tmp_path / "app" / "build.gradle.kts",
            "dependencies { implementation(libs.androidx.core.ktx) }",
        )
        result = GradleModuleScanner().scan(tmp_path, _catalog("androidx-core-ktx"))
        assert result is not None
        usages = {u.alias: u for u in result.library_usages}
        assert ":app" in usages["androidx-core-ktx"].implementation_modules
