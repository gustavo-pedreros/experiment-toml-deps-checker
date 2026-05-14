"""Unit tests for GradleModuleScanner.

All tests use ``tmp_path`` (pytest fixture) — no network, no real Gradle projects.
"""

from __future__ import annotations

from pathlib import Path

from gradle_deps_monitor.domain.catalog import Bundle, Catalog, Library
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


def _catalog_with_bundles(
    libraries: tuple[str, ...],
    bundles: tuple[tuple[str, tuple[str, ...]], ...],
) -> Catalog:
    """Build a Catalog with libraries + ``(bundle_alias, members)`` pairs."""
    libs = tuple(
        Library(
            alias=alias,
            group="com.example",
            artifact=alias,
            version=MavenVersion("1.0.0"),
        )
        for alias in libraries
    )
    bundle_objs = tuple(Bundle(alias=alias, member_aliases=members) for alias, members in bundles)
    return Catalog(
        source_path=Path("/fake/gradle/libs.versions.toml"),
        libraries=libs,
        plugins=(),
        bundles=bundle_objs,
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


# ---------------------------------------------------------------------------
# RFC-0019 PR #1 — camelCase accessor recognition
# ---------------------------------------------------------------------------


from gradle_deps_monitor.infrastructure.scanners.gradle_module_scanner import (  # noqa: E402
    _alias_to_camel,
    _build_accessor_map,
)


class TestAliasToCamel:
    """Gradle generates camelCase from kebab aliases by lowercasing the
    first segment and title-casing every subsequent segment.
    """

    def test_single_word(self) -> None:
        assert _alias_to_camel("retrofit") == "retrofit"

    def test_two_segments(self) -> None:
        assert _alias_to_camel("core-ktx") == "coreKtx"

    def test_three_segments(self) -> None:
        assert _alias_to_camel("androidx-core-ktx") == "androidxCoreKtx"

    def test_already_camel_remains_camel(self) -> None:
        # No hyphens → input is returned as-is.
        assert _alias_to_camel("okHttp") == "okhttp"

    def test_empty_segments_dropped(self) -> None:
        # Leading / trailing / consecutive hyphens are silently coalesced.
        assert _alias_to_camel("--foo--bar--") == "fooBar"

    def test_empty_alias_returns_input(self) -> None:
        assert _alias_to_camel("") == ""


class TestBuildAccessorMap:
    """The reverse-lookup map must cover BOTH accessor forms so that
    KTS-style ``libs.fooBar`` and Groovy-style ``libs.foo.bar`` both
    resolve to the same catalog alias.
    """

    def test_contains_dotted_form(self) -> None:
        m = _build_accessor_map(_catalog("androidx-core-ktx"))
        assert m["androidx.core.ktx"] == "androidx-core-ktx"

    def test_contains_camel_form(self) -> None:
        m = _build_accessor_map(_catalog("androidx-core-ktx"))
        assert m["androidxCoreKtx"] == "androidx-core-ktx"

    def test_single_word_alias_same_under_both_forms(self) -> None:
        m = _build_accessor_map(_catalog("retrofit"))
        # Both forms collapse to "retrofit"; one key, one value.
        assert m == {"retrofit": "retrofit"}

    def test_multiple_libraries(self) -> None:
        m = _build_accessor_map(_catalog("retrofit", "androidx-core-ktx", "core-ktx"))
        # Five distinct accessor strings (retrofit + two pairs).
        assert m["retrofit"] == "retrofit"
        assert m["androidx.core.ktx"] == "androidx-core-ktx"
        assert m["androidxCoreKtx"] == "androidx-core-ktx"
        assert m["core.ktx"] == "core-ktx"
        assert m["coreKtx"] == "core-ktx"


class TestGradleModuleScannerCamelCase:
    """End-to-end: a KTS build file using ``libs.fooBar`` produces a
    non-zero usage count. This is the regression target — pre-PR #1 the
    scanner returned 0 here.
    """

    def test_camel_case_accessor_detected(self, tmp_path: Path) -> None:
        _write(tmp_path / "settings.gradle.kts", 'include(":app")')
        _write(
            tmp_path / "app" / "build.gradle.kts",
            "dependencies { implementation(libs.androidxCoreKtx) }",
        )
        result = GradleModuleScanner().scan(tmp_path, _catalog("androidx-core-ktx"))
        assert result is not None
        usages = {u.alias: u for u in result.library_usages}
        assert ":app" in usages["androidx-core-ktx"].implementation_modules

    def test_mixed_camel_and_dotted_in_same_project(self, tmp_path: Path) -> None:
        _write(
            tmp_path / "settings.gradle.kts",
            'include(":app")\ninclude(":feature")',
        )
        _write(
            tmp_path / "app" / "build.gradle.kts",
            "dependencies { implementation(libs.androidxCoreKtx) }",
        )
        _write(
            tmp_path / "feature" / "build.gradle.kts",
            "dependencies { implementation(libs.androidx.core.ktx) }",
        )
        result = GradleModuleScanner().scan(tmp_path, _catalog("androidx-core-ktx"))
        assert result is not None
        usages = {u.alias: u for u in result.library_usages}
        assert ":app" in usages["androidx-core-ktx"].implementation_modules
        assert ":feature" in usages["androidx-core-ktx"].implementation_modules

    def test_camel_case_in_kts_with_string_quotes(self, tmp_path: Path) -> None:
        """``api libs.fooBar`` (Groovy without parens) — same regex path."""
        _write(tmp_path / "settings.gradle", "include ':app'")
        _write(
            tmp_path / "app" / "build.gradle",
            "dependencies {\n    api libs.androidxCoreKtx\n}",
        )
        result = GradleModuleScanner().scan(tmp_path, _catalog("androidx-core-ktx"))
        assert result is not None
        usages = {u.alias: u for u in result.library_usages}
        assert ":app" in usages["androidx-core-ktx"].api_modules


# ---------------------------------------------------------------------------
# RFC-0019 PR #1 — malformed-file resilience (MOD-001)
# ---------------------------------------------------------------------------


class TestGradleModuleScannerMalformedFile:
    """A binary or otherwise unreadable build file must not crash the
    scan. Each affected module emits one ``MOD-001`` finding; the rest
    of the project continues to scan.
    """

    def test_binary_build_file_emits_mod_001(self, tmp_path: Path) -> None:
        _write(tmp_path / "settings.gradle.kts", 'include(":app")\ninclude(":corrupt")')
        _write(
            tmp_path / "app" / "build.gradle.kts",
            "dependencies { implementation(libs.retrofit) }",
        )
        # :corrupt has a build file containing bytes that aren't valid UTF-8.
        corrupt_path = tmp_path / "corrupt" / "build.gradle.kts"
        corrupt_path.parent.mkdir(parents=True, exist_ok=True)
        corrupt_path.write_bytes(b"\xff\xfe\x00\x80 not valid utf-8 \xc3\x28")

        result = GradleModuleScanner().scan(tmp_path, _catalog("retrofit"))
        assert result is not None
        rule_ids = [f.rule_id for f in result.findings]
        assert "MOD-001" in rule_ids

    def test_scan_continues_after_corrupt_module(self, tmp_path: Path) -> None:
        """Healthy modules are still scanned after a corrupt sibling."""
        _write(tmp_path / "settings.gradle.kts", 'include(":corrupt")\ninclude(":app")')
        corrupt_path = tmp_path / "corrupt" / "build.gradle.kts"
        corrupt_path.parent.mkdir(parents=True, exist_ok=True)
        corrupt_path.write_bytes(b"\xff\xfe\x00")
        _write(
            tmp_path / "app" / "build.gradle.kts",
            "dependencies { implementation(libs.retrofit) }",
        )

        result = GradleModuleScanner().scan(tmp_path, _catalog("retrofit"))
        assert result is not None
        usages = {u.alias: u for u in result.library_usages}
        # :app was still scanned despite the corrupt :corrupt module.
        assert ":app" in usages["retrofit"].implementation_modules

    def test_mod_001_message_includes_module_path(self, tmp_path: Path) -> None:
        _write(tmp_path / "settings.gradle.kts", 'include(":bad")')
        bad = tmp_path / "bad" / "build.gradle.kts"
        bad.parent.mkdir(parents=True, exist_ok=True)
        bad.write_bytes(b"\xff\xfe\x00")
        result = GradleModuleScanner().scan(tmp_path, _catalog("retrofit"))
        assert result is not None
        assert len(result.findings) == 1
        finding = result.findings[0]
        assert finding.rule_id == "MOD-001"
        assert ":bad" in finding.message

    def test_healthy_scan_emits_no_findings(self, tmp_path: Path) -> None:
        """Default invariant: no corrupt files → empty findings tuple."""
        _write(tmp_path / "settings.gradle.kts", 'include(":app")')
        _write(
            tmp_path / "app" / "build.gradle.kts",
            "dependencies { implementation(libs.retrofit) }",
        )
        result = GradleModuleScanner().scan(tmp_path, _catalog("retrofit"))
        assert result is not None
        assert result.findings == ()


# ---------------------------------------------------------------------------
# RFC-0019 PR #2 — bundle attribution
# ---------------------------------------------------------------------------


from gradle_deps_monitor.infrastructure.scanners.gradle_module_scanner import (  # noqa: E402
    _build_bundle_accessor_map,
)


class TestBuildBundleAccessorMap:
    """Bundle accessor map populates both dotted and camelCase forms,
    each pointing at the full member-alias tuple.
    """

    def test_single_word_bundle(self) -> None:
        catalog = _catalog_with_bundles(
            ("retrofit", "okhttp"),
            (("network", ("retrofit", "okhttp")),),
        )
        m = _build_bundle_accessor_map(catalog)
        # Single-word alias collapses to one key under both forms.
        assert m == {"bundles.network": ("retrofit", "okhttp")}

    def test_two_segment_bundle(self) -> None:
        catalog = _catalog_with_bundles(
            ("a", "b"),
            (("compose-ui", ("a", "b")),),
        )
        m = _build_bundle_accessor_map(catalog)
        assert m["bundles.compose.ui"] == ("a", "b")
        assert m["bundles.composeUi"] == ("a", "b")

    def test_multiple_bundles(self) -> None:
        catalog = _catalog_with_bundles(
            ("a", "b", "c", "d"),
            (
                ("network", ("a", "b")),
                ("compose-ui", ("c", "d")),
            ),
        )
        m = _build_bundle_accessor_map(catalog)
        assert m["bundles.network"] == ("a", "b")
        assert m["bundles.compose.ui"] == ("c", "d")
        assert m["bundles.composeUi"] == ("c", "d")

    def test_empty_catalog_returns_empty(self) -> None:
        m = _build_bundle_accessor_map(_catalog())
        assert m == {}


class TestGradleModuleScannerBundleAttribution:
    """End-to-end: ``libs.bundles.<name>`` credits every member library."""

    def test_bundle_credits_all_members(self, tmp_path: Path) -> None:
        _write(tmp_path / "settings.gradle.kts", 'include(":app")')
        _write(
            tmp_path / "app" / "build.gradle.kts",
            "dependencies { implementation(libs.bundles.network) }",
        )
        catalog = _catalog_with_bundles(
            ("retrofit", "okhttp", "moshi"),
            (("network", ("retrofit", "okhttp", "moshi")),),
        )
        result = GradleModuleScanner().scan(tmp_path, catalog)
        assert result is not None
        usages = {u.alias: u for u in result.library_usages}
        for member in ("retrofit", "okhttp", "moshi"):
            assert ":app" in usages[member].implementation_modules, (
                f"{member} should be credited via bundle"
            )

    def test_bundle_camel_case_accessor(self, tmp_path: Path) -> None:
        """``libs.bundles.composeUi`` (KTS form) is recognised."""
        _write(tmp_path / "settings.gradle.kts", 'include(":app")')
        _write(
            tmp_path / "app" / "build.gradle.kts",
            "dependencies { implementation(libs.bundles.composeUi) }",
        )
        catalog = _catalog_with_bundles(
            ("androidx-compose-ui", "androidx-compose-material"),
            (("compose-ui", ("androidx-compose-ui", "androidx-compose-material")),),
        )
        result = GradleModuleScanner().scan(tmp_path, catalog)
        assert result is not None
        usages = {u.alias: u for u in result.library_usages}
        assert ":app" in usages["androidx-compose-ui"].implementation_modules
        assert ":app" in usages["androidx-compose-material"].implementation_modules

    def test_bundle_dotted_accessor(self, tmp_path: Path) -> None:
        """``libs.bundles.compose.ui`` (Groovy / multi-segment) is recognised."""
        _write(tmp_path / "settings.gradle", "include ':app'")
        _write(
            tmp_path / "app" / "build.gradle",
            "dependencies { implementation libs.bundles.compose.ui }",
        )
        catalog = _catalog_with_bundles(
            ("androidx-compose-ui", "androidx-compose-material"),
            (("compose-ui", ("androidx-compose-ui", "androidx-compose-material")),),
        )
        result = GradleModuleScanner().scan(tmp_path, catalog)
        assert result is not None
        usages = {u.alias: u for u in result.library_usages}
        assert ":app" in usages["androidx-compose-ui"].implementation_modules
        assert ":app" in usages["androidx-compose-material"].implementation_modules

    def test_bundle_respects_configuration(self, tmp_path: Path) -> None:
        """Members are credited under the bucket of the bundle declaration."""
        _write(tmp_path / "settings.gradle.kts", 'include(":app")')
        _write(
            tmp_path / "app" / "build.gradle.kts",
            "dependencies {\n"
            "    api(libs.bundles.network)\n"
            "    testImplementation(libs.bundles.testing)\n"
            "}",
        )
        catalog = _catalog_with_bundles(
            ("retrofit", "okhttp", "junit", "mockk"),
            (
                ("network", ("retrofit", "okhttp")),
                ("testing", ("junit", "mockk")),
            ),
        )
        result = GradleModuleScanner().scan(tmp_path, catalog)
        assert result is not None
        usages = {u.alias: u for u in result.library_usages}
        assert ":app" in usages["retrofit"].api_modules
        assert ":app" in usages["okhttp"].api_modules
        assert ":app" in usages["junit"].test_modules
        assert ":app" in usages["mockk"].test_modules
        # And nothing leaked into the wrong bucket.
        assert ":app" not in usages["retrofit"].implementation_modules
        assert ":app" not in usages["junit"].api_modules

    def test_bundle_does_not_double_count_when_also_declared_directly(self, tmp_path: Path) -> None:
        """A module that declares ``libs.retrofit`` AND a bundle containing
        retrofit must credit retrofit exactly once in the impl bucket.
        """
        _write(tmp_path / "settings.gradle.kts", 'include(":app")')
        _write(
            tmp_path / "app" / "build.gradle.kts",
            "dependencies {\n"
            "    implementation(libs.retrofit)\n"
            "    implementation(libs.bundles.network)\n"
            "}",
        )
        catalog = _catalog_with_bundles(
            ("retrofit", "okhttp"),
            (("network", ("retrofit", "okhttp")),),
        )
        result = GradleModuleScanner().scan(tmp_path, catalog)
        assert result is not None
        usages = {u.alias: u for u in result.library_usages}
        # retrofit appears in the impl list for :app exactly once.
        assert usages["retrofit"].implementation_modules.count(":app") == 1
        # okhttp also credited once (only via the bundle).
        assert usages["okhttp"].implementation_modules.count(":app") == 1

    def test_module_direct_count_reflects_bundle_expansion(self, tmp_path: Path) -> None:
        """A bundle declaration counts as ``N`` direct deps for the module,
        where ``N`` is the number of unique libraries credited (matching how
        Gradle resolves the dependency graph at compile time).
        """
        _write(tmp_path / "settings.gradle.kts", 'include(":app")')
        _write(
            tmp_path / "app" / "build.gradle.kts",
            "dependencies { implementation(libs.bundles.network) }",
        )
        catalog = _catalog_with_bundles(
            ("retrofit", "okhttp", "moshi"),
            (("network", ("retrofit", "okhttp", "moshi")),),
        )
        result = GradleModuleScanner().scan(tmp_path, catalog)
        assert result is not None
        counts = {s.module_path: s.direct_dep_count for s in result.module_summaries}
        # 3 distinct libs credited via the bundle, 3 direct deps.
        assert counts[":app"] == 3

    def test_unknown_bundle_member_ignored(self, tmp_path: Path) -> None:
        """A bundle that references an alias not in the catalog must not
        crash the scan. ``HDX-002`` flags the catalog problem separately.
        """
        _write(tmp_path / "settings.gradle.kts", 'include(":app")')
        _write(
            tmp_path / "app" / "build.gradle.kts",
            "dependencies { implementation(libs.bundles.network) }",
        )
        catalog = _catalog_with_bundles(
            ("retrofit",),  # okhttp missing!
            (("network", ("retrofit", "okhttp")),),
        )
        result = GradleModuleScanner().scan(tmp_path, catalog)
        assert result is not None
        usages = {u.alias: u for u in result.library_usages}
        # retrofit credited; okhttp absent from the usage map entirely.
        assert ":app" in usages["retrofit"].implementation_modules
        assert "okhttp" not in usages

    def test_unused_bundle_does_not_credit_members(self, tmp_path: Path) -> None:
        """A catalog can declare bundles that no module references; those
        member libraries should keep their zero-usage status.
        """
        _write(tmp_path / "settings.gradle.kts", 'include(":app")')
        _write(
            tmp_path / "app" / "build.gradle.kts",
            "dependencies { implementation(libs.retrofit) }",
        )
        catalog = _catalog_with_bundles(
            ("retrofit", "okhttp"),
            (("network", ("retrofit", "okhttp")),),  # bundle declared but unused
        )
        result = GradleModuleScanner().scan(tmp_path, catalog)
        assert result is not None
        usages = {u.alias: u for u in result.library_usages}
        # okhttp was not used directly, and the bundle was not referenced.
        assert usages["okhttp"].total_count == 0

    def test_bundle_in_mixed_kts_groovy_project(self, tmp_path: Path) -> None:
        """One module uses the bundle in KTS-camel form, another in Groovy
        dotted form — both modules credit every member.
        """
        _write(
            tmp_path / "settings.gradle.kts",
            'include(":app")\ninclude(":feature:auth")',
        )
        _write(
            tmp_path / "app" / "build.gradle.kts",
            "dependencies { implementation(libs.bundles.composeUi) }",
        )
        _write(
            tmp_path / "feature" / "auth" / "build.gradle",
            "dependencies { implementation libs.bundles.compose.ui }",
        )
        catalog = _catalog_with_bundles(
            ("compose-ui-core", "compose-ui-material"),
            (("compose-ui", ("compose-ui-core", "compose-ui-material")),),
        )
        result = GradleModuleScanner().scan(tmp_path, catalog)
        assert result is not None
        usages = {u.alias: u for u in result.library_usages}
        for member in ("compose-ui-core", "compose-ui-material"):
            assert ":app" in usages[member].implementation_modules
            assert ":feature:auth" in usages[member].implementation_modules
