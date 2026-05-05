"""Unit tests for gradle_deps_monitor.domain.module_usage."""

from __future__ import annotations

import pytest

from gradle_deps_monitor.domain.module_usage import LibraryUsage, ModuleSummary, ModuleUsageMap


def _usage(
    alias: str = "retrofit",
    impl: tuple[str, ...] = (),
    api: tuple[str, ...] = (),
    test: tuple[str, ...] = (),
) -> LibraryUsage:
    return LibraryUsage(
        alias=alias,
        coordinate=f"com.example:{alias}",
        implementation_modules=impl,
        api_modules=api,
        test_modules=test,
    )


class TestLibraryUsage:
    def test_direct_count_impl_only(self) -> None:
        u = _usage(impl=(":app", ":feature:auth"))
        assert u.direct_count == 2

    def test_direct_count_api_only(self) -> None:
        u = _usage(api=(":network:core",))
        assert u.direct_count == 1

    def test_direct_count_impl_and_api(self) -> None:
        u = _usage(impl=(":app",), api=(":network:core",))
        assert u.direct_count == 2

    def test_direct_count_test_not_counted(self) -> None:
        u = _usage(test=(":app",))
        assert u.direct_count == 0

    def test_api_count(self) -> None:
        u = _usage(api=(":a", ":b"))
        assert u.api_count == 2

    def test_test_only_count_pure_test(self) -> None:
        u = _usage(test=(":app", ":feature"))
        assert u.test_only_count == 2

    def test_test_only_count_zero_when_also_impl(self) -> None:
        u = _usage(impl=(":app",), test=(":test-module",))
        assert u.test_only_count == 0

    def test_total_count(self) -> None:
        u = _usage(impl=(":a",), api=(":b",), test=(":c", ":d"))
        assert u.total_count == 4

    def test_frozen(self) -> None:
        u = _usage()
        with pytest.raises(AttributeError):
            u.alias = "other"  # type: ignore[misc]

    def test_zero_usage(self) -> None:
        u = _usage()
        assert u.direct_count == 0
        assert u.total_count == 0
        assert u.test_only_count == 0


class TestModuleUsageMap:
    def _make(self) -> ModuleUsageMap:
        return ModuleUsageMap(
            library_usages=(
                _usage("retrofit", impl=(":app", ":feature")),
                _usage("junit", test=(":app",)),
                _usage("unused"),
            ),
            module_summaries=(
                ModuleSummary(":app", 1),
                ModuleSummary(":feature", 1),
                ModuleSummary(":network", 5),
            ),
            modules_scanned=3,
        )

    def test_libraries_in_use_filters_zero(self) -> None:
        m = self._make()
        aliases = {u.alias for u in m.libraries_in_use()}
        assert aliases == {"retrofit", "junit"}
        assert "unused" not in aliases

    def test_top_modules_sorted_by_count(self) -> None:
        m = self._make()
        top = m.top_modules(3)
        assert top[0].module_path == ":network"
        assert top[0].direct_dep_count == 5

    def test_top_modules_capped_at_n(self) -> None:
        m = self._make()
        top = m.top_modules(2)
        assert len(top) == 2

    def test_top_modules_all_when_fewer_than_n(self) -> None:
        m = self._make()
        top = m.top_modules(100)
        assert len(top) == 3

    def test_modules_scanned(self) -> None:
        m = self._make()
        assert m.modules_scanned == 3

    def test_frozen(self) -> None:
        m = self._make()
        with pytest.raises(AttributeError):
            m.modules_scanned = 99  # type: ignore[misc]
