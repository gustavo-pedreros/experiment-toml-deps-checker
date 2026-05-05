"""Module usage map domain model (RFC-0007).

Value objects produced by scanning ``build.gradle(.kts)`` files and
cross-referencing them against the version catalog.  Pure data; no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LibraryUsage:
    """Usage of a single catalog library across all scanned Gradle modules.

    :param alias: Catalog alias (e.g. ``retrofit``).
    :param coordinate: Maven coordinate (e.g. ``com.squareup.retrofit2:retrofit``).
    :param implementation_modules: Modules declaring this library via
        ``implementation``, ``runtimeOnly``, ``debugImplementation``,
        ``ksp``, ``kapt``, etc. (non-ABI-exposing, non-test).
    :param api_modules: Modules declaring via ``api`` or ``compileOnly``
        — these expose the library on their own compile classpath (ABI leak risk).
    :param test_modules: Modules declaring via ``testImplementation``,
        ``androidTestImplementation``, ``testRuntimeOnly``, etc.
    """

    alias: str
    coordinate: str
    implementation_modules: tuple[str, ...]
    api_modules: tuple[str, ...]
    test_modules: tuple[str, ...]

    @property
    def direct_count(self) -> int:
        """Number of modules using this library in non-test configurations."""
        return len(self.implementation_modules) + len(self.api_modules)

    @property
    def api_count(self) -> int:
        """Number of modules exposing this library via ``api``/``compileOnly``."""
        return len(self.api_modules)

    @property
    def test_only_count(self) -> int:
        """Number of modules using this library only in test configurations."""
        # Only count as test-only if it does NOT appear in impl/api
        if self.implementation_modules or self.api_modules:
            return 0
        return len(self.test_modules)

    @property
    def total_count(self) -> int:
        """Total modules referencing this library in any configuration."""
        return len(self.implementation_modules) + len(self.api_modules) + len(self.test_modules)


@dataclass(frozen=True)
class ModuleSummary:
    """Dependency-count summary for a single Gradle module.

    :param module_path: Gradle module path, e.g. ``:feature:auth``.
    :param direct_dep_count: Number of catalog libraries used in non-test
        configurations (``implementation`` + ``api`` + similar).
    """

    module_path: str
    direct_dep_count: int


@dataclass(frozen=True)
class ModuleUsageMap:
    """Aggregate result of a module usage scan.

    :param library_usages: One :class:`LibraryUsage` per catalog library,
        including those with zero usage (``total_count == 0``).
    :param module_summaries: One :class:`ModuleSummary` per scanned module.
    :param modules_scanned: Total number of modules whose build files were
        successfully read (modules with no build file are excluded).
    """

    library_usages: tuple[LibraryUsage, ...]
    module_summaries: tuple[ModuleSummary, ...]
    modules_scanned: int

    def libraries_in_use(self) -> tuple[LibraryUsage, ...]:
        """Return only libraries referenced by at least one module."""
        return tuple(u for u in self.library_usages if u.total_count > 0)

    def top_modules(self, n: int = 10) -> tuple[ModuleSummary, ...]:
        """Return the top-*n* modules sorted by descending direct dependency count."""
        return tuple(sorted(self.module_summaries, key=lambda m: -m.direct_dep_count)[:n])
