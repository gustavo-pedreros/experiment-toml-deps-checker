"""GradleModuleScanner — static parser for Gradle build files (RFC-0007).

Pipeline
--------
1. Walk up from *catalog_path* to find ``settings.gradle(.kts)``.
2. Parse ``include(...)`` calls to enumerate module paths.
3. For each module, locate ``build.gradle(.kts)`` and extract dependency
   declarations that reference ``libs.<accessor>``.
4. Map the dotted accessor back to the catalog alias via a pre-built
   reverse lookup table.
5. Aggregate into a :class:`~...domain.module_usage.ModuleUsageMap`.

Accessor mapping
----------------
Gradle generates a dotted accessor from the catalog alias by replacing
every ``-`` with ``.`` and lowercasing:
``androidx-core-ktx`` → ``libs.androidx.core.ktx``.

This scanner only recognises the **dotted** form.  The camelCase form
(``libs.androidxCoreKtx``) used by some KTS type-safe blocks is not
matched by this first-cut implementation.

Configuration classification
-----------------------------
* **api** — ``api``, ``compileOnly``
* **test** — ``testImplementation``, ``androidTestImplementation``,
  ``testRuntimeOnly``, ``testCompileOnly``
* **impl** — everything else: ``implementation``, ``runtimeOnly``,
  ``debugImplementation``, ``releaseImplementation``,
  ``ksp``, ``kapt``, ``annotationProcessor``
"""

from __future__ import annotations

import re
from pathlib import Path

from gradle_deps_monitor.domain.catalog import Catalog
from gradle_deps_monitor.domain.module_usage import LibraryUsage, ModuleSummary, ModuleUsageMap

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SETTINGS_FILES = ("settings.gradle.kts", "settings.gradle")
_BUILD_FILES = ("build.gradle.kts", "build.gradle")

# Maximum directory levels to walk up when searching for settings file.
_MAX_SEARCH_DEPTH = 4

# Matches quoted strings inside include() calls.
_INCLUDE_STRING_RE = re.compile(r"""["'](:?[a-zA-Z0-9_:.-]+)["']""")

# Matches dependency declarations referencing libs.<accessor>.
# Groups: (1) configuration name, (2) dotted accessor after "libs."
_DEP_RE = re.compile(
    r"(?:^|[(\s,])"
    r"(implementation|api|testImplementation|androidTestImplementation"
    r"|testRuntimeOnly|testCompileOnly|debugImplementation|releaseImplementation"
    r"|compileOnly|runtimeOnly|ksp|kapt|annotationProcessor)"
    r"\s*\(?\s*libs\.([a-zA-Z0-9_.]+)",
    re.MULTILINE,
)

_API_CONFIGS: frozenset[str] = frozenset({"api", "compileOnly"})
_TEST_CONFIGS: frozenset[str] = frozenset(
    {
        "testImplementation",
        "androidTestImplementation",
        "testRuntimeOnly",
        "testCompileOnly",
    }
)

# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def _alias_to_accessor(alias: str) -> str:
    """Return the dotted accessor form for *alias* (``-`` → ``.``, lowercased)."""
    return alias.replace("-", ".").lower()


def _build_accessor_map(catalog: Catalog) -> dict[str, str]:
    """Return ``{normalized_accessor: alias}`` for every catalog library."""
    return {_alias_to_accessor(lib.alias): lib.alias for lib in catalog.libraries}


def _find_project_root(catalog_path: Path) -> Path | None:
    """Walk up from *catalog_path* looking for ``settings.gradle(.kts)``.

    Returns the directory containing the settings file, or ``None``.
    """
    candidate = catalog_path if catalog_path.is_dir() else catalog_path.parent
    for _ in range(_MAX_SEARCH_DEPTH):
        for name in _SETTINGS_FILES:
            if (candidate / name).is_file():
                return candidate
        parent = candidate.parent
        if parent == candidate:
            break
        candidate = parent
    return None


def _parse_module_paths(settings_text: str) -> list[str]:
    """Extract Gradle module paths from a settings file.

    Handles both KTS and Groovy forms::

        include(":app")
        include(":feature:auth", ":feature:payments")
        include ':app'              // Groovy
        include ':app', ':feature'  // Groovy multi-arg

    Returns a list of colon-prefixed paths, e.g. ``[":app", ":feature:auth"]``.
    """
    paths: list[str] = []
    for line in settings_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("//"):
            continue
        if "include" not in stripped:
            continue
        for m in _INCLUDE_STRING_RE.finditer(stripped):
            raw = m.group(1)
            if raw.startswith(":"):
                paths.append(raw)
            elif re.match(r"^[a-zA-Z]", raw) and "/" not in raw:
                # bare name without leading colon
                paths.append(f":{raw}")
    return paths


def _module_dir(project_root: Path, module_path: str) -> Path:
    """Convert ``:feature:auth`` to ``project_root/feature/auth``."""
    rel = module_path.lstrip(":").replace(":", "/")
    return project_root / rel


def _find_build_file(module_dir: Path) -> Path | None:
    for name in _BUILD_FILES:
        p = module_dir / name
        if p.is_file():
            return p
    return None


def _classify_config(config: str) -> str:
    """Return ``"api"``, ``"test"``, or ``"impl"`` for a configuration name."""
    if config in _API_CONFIGS:
        return "api"
    if config in _TEST_CONFIGS:
        return "test"
    return "impl"


# ---------------------------------------------------------------------------
# GradleModuleScanner
# ---------------------------------------------------------------------------


class GradleModuleScanner:
    """Scans Gradle build files to produce a :class:`~...domain.module_usage.ModuleUsageMap`.

    This is a **static** scanner — it never invokes the Gradle daemon.
    It reads ``build.gradle(.kts)`` files directly using regex-based
    parsing.  Accuracy is high for the common single-line declaration
    patterns; multi-line and programmatic declarations may be missed.
    """

    def scan(self, catalog_path: Path, catalog: Catalog) -> ModuleUsageMap | None:
        """Run the scan and return a :class:`ModuleUsageMap`, or ``None`` on failure.

        :param catalog_path: Directory (or file) where ``libs.versions.toml`` lives.
        :param catalog: Already-parsed version catalog for alias lookup.
        :returns: ``None`` when ``settings.gradle(.kts)`` cannot be found or
            no ``include()`` declarations are present.
        """
        project_root = _find_project_root(catalog_path)
        if project_root is None:
            return None

        settings_file = next(
            (project_root / n for n in _SETTINGS_FILES if (project_root / n).is_file()),
            None,
        )
        if settings_file is None:
            return None  # pragma: no cover — already found above

        try:
            settings_text = settings_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None

        module_paths = _parse_module_paths(settings_text)
        if not module_paths:
            return None

        accessor_map = _build_accessor_map(catalog)

        # alias → {"impl": [...], "api": [...], "test": [...]}
        usage: dict[str, dict[str, list[str]]] = {
            lib.alias: {"impl": [], "api": [], "test": []} for lib in catalog.libraries
        }
        module_direct_counts: dict[str, int] = {}

        for module_path in module_paths:
            module_dir = _module_dir(project_root, module_path)
            build_file = _find_build_file(module_dir)
            if build_file is None:
                continue

            try:
                text = build_file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            direct_count = 0

            for m in _DEP_RE.finditer(text):
                config = m.group(1)
                accessor = m.group(2).lower()
                alias = accessor_map.get(accessor)
                if alias is None:
                    continue

                bucket = _classify_config(config)
                buckets = usage[alias]
                if module_path not in buckets[bucket]:
                    buckets[bucket].append(module_path)
                    if bucket != "test":
                        direct_count += 1

            module_direct_counts[module_path] = direct_count

        library_usages = tuple(
            LibraryUsage(
                alias=lib.alias,
                coordinate=lib.coordinate,
                implementation_modules=tuple(sorted(usage[lib.alias]["impl"])),
                api_modules=tuple(sorted(usage[lib.alias]["api"])),
                test_modules=tuple(sorted(usage[lib.alias]["test"])),
            )
            for lib in sorted(catalog.libraries, key=lambda lb: lb.alias)
        )

        module_summaries = tuple(
            ModuleSummary(module_path=path, direct_dep_count=count)
            for path, count in sorted(module_direct_counts.items())
        )

        return ModuleUsageMap(
            library_usages=library_usages,
            module_summaries=module_summaries,
            modules_scanned=len(module_direct_counts),
        )
