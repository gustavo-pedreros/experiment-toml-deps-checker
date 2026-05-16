"""GradleModuleScanner — static parser for Gradle build files (RFC-0007 / RFC-0019).

Pipeline
--------
1. Walk up from *catalog_path* to find ``settings.gradle(.kts)``.
2. Parse ``include(...)`` calls to enumerate module paths.
3. For each module, locate ``build.gradle(.kts)`` and extract dependency
   declarations that reference ``libs.<accessor>``. Per-module work
   (read + regex + classify) runs **in parallel** via
   ``asyncio.to_thread`` (RFC-0019 PR #3) so a 200-module project no
   longer pays a serialised read for every build file.
4. Map the accessor back to the catalog alias via a pre-built reverse
   lookup table that covers **both** the dotted and camelCase forms
   (RFC-0019 PR #1). Bundle accessors (``libs.bundles.<form>``) are
   resolved through a second lookup table that expands to the bundle's
   member library aliases (RFC-0019 PR #2).
5. Aggregate into a :class:`~...domain.module_usage.ModuleUsageMap`.

Accessor mapping
----------------
Gradle generates two equivalent accessors from a kebab-case catalog
alias:

- **Dotted** form (``-`` → ``.``, lowercased):
  ``androidx-core-ktx`` → ``libs.androidx.core.ktx``.
- **camelCase** form (first segment lowercased; subsequent segments
  title-cased and concatenated):
  ``androidx-core-ktx`` → ``libs.androidxCoreKtx``.

The camelCase form is the canonical accessor in Kotlin DSL type-safe
blocks, so KTS-heavy projects rely on it heavily. PR #1 of RFC-0019
added recognition for both forms; before this change, KTS projects had
their usage counts systematically under-reported.

Bundle attribution (PR #2)
--------------------------
Bundles are accessed under the reserved ``libs.bundles.`` namespace.
For a bundle alias ``compose-ui`` with members ``[androidx-compose-ui,
androidx-compose-material]``, Gradle generates two equivalent
accessors::

    libs.bundles.compose.ui   // dotted form
    libs.bundles.composeUi    // camelCase form

When the scanner matches either form, **every member library** listed
in the bundle is credited for that module under the configuration the
bundle was declared with (``implementation``, ``api``, etc.). A library
referenced both directly and via a bundle in the same module is
credited only once — dedup happens naturally through the per-module
"already in bucket" check.

Configuration classification
-----------------------------
* **api** — ``api``, ``compileOnly``
* **test** — ``testImplementation``, ``androidTestImplementation``,
  ``testRuntimeOnly``, ``testCompileOnly``
* **impl** — everything else: ``implementation``, ``runtimeOnly``,
  ``debugImplementation``, ``releaseImplementation``,
  ``ksp``, ``kapt``, ``annotationProcessor``

Resilience
----------
A single unreadable ``build.gradle(.kts)`` file (binary garbage, broken
encoding, permission error) no longer poisons the entire scan. Each
affected module produces a ``MOD-001`` :class:`Finding`; the scan
continues over the rest of the project. Findings are merged into
:attr:`FreezeReport.health_findings` by the application layer.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from pathlib import Path

from gradle_deps_monitor.domain.catalog import Catalog
from gradle_deps_monitor.domain.finding import Finding, Severity
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

# Separator characters that Gradle's catalog accessor convention treats
# as equivalent: ``-`` and ``_`` both produce nesting in the generated
# type-safe accessor (so ``foo_bar`` and ``foo-bar`` both become
# ``libs.foo.bar`` / ``libs.fooBar``). RFC-0022 added ``_`` after
# real-world projects with underscore-only aliases were silently
# under-counted.
_SEPARATORS_RE = re.compile(r"[-_]")

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
    """Return the dotted accessor form for *alias* (``-``/``_`` → ``.``, lowercased).

    Both ``-`` and ``_`` are treated as separators per Gradle's catalog
    accessor convention; ``foo_bar_baz`` and ``foo-bar-baz`` both yield
    ``"foo.bar.baz"``. RFC-0022 added underscore support; pre-RFC-0022
    underscore-only aliases never matched the dotted accessors used in
    build files. ``_alias_to_camel`` is the camelCase sibling
    introduced by RFC-0019 PR #1.
    """
    return _SEPARATORS_RE.sub(".", alias).lower()


def _alias_to_camel(alias: str) -> str:
    """Return the camelCase accessor form for *alias*.

    The first segment is lowercased; every subsequent segment is
    title-cased and concatenated::

        "androidx-core-ktx" → "androidxCoreKtx"
        "internal_sdk_lib"  → "internalSdkLib"
        "retrofit"          → "retrofit"
        "okhttp"            → "okhttp"

    Both ``-`` and ``_`` split as separators per Gradle's catalog
    convention (RFC-0022). Empty segments (from leading / trailing /
    consecutive separators) are dropped, matching Gradle's behaviour
    for malformed aliases.
    """
    parts = [p for p in _SEPARATORS_RE.split(alias) if p]
    if not parts:
        return alias
    head = parts[0].lower()
    tail = "".join(p[:1].upper() + p[1:].lower() for p in parts[1:])
    return head + tail


def _build_accessor_map(catalog: Catalog) -> dict[str, str]:
    """Return ``{accessor: alias}`` covering both dotted and camelCase forms.

    Each catalog library contributes two entries — its dotted accessor
    (``androidx.core.ktx``) and its camelCase accessor
    (``androidxCoreKtx``). Both map back to the same alias, so the
    scanner can recognise either form in a build file. Keys are stored
    verbatim (no lowercasing) so the camelCase lookup remains
    case-sensitive — Gradle's generated accessors are deterministic in
    case, so this matches reality.

    If a single alias somehow produces the same string in both forms
    (e.g. a single-word alias like ``retrofit``), the duplicate write is
    a harmless no-op.
    """
    mapping: dict[str, str] = {}
    for lib in catalog.libraries:
        mapping[_alias_to_accessor(lib.alias)] = lib.alias
        mapping[_alias_to_camel(lib.alias)] = lib.alias
    return mapping


def _build_bundle_accessor_map(catalog: Catalog) -> dict[str, tuple[str, ...]]:
    """Return ``{accessor: member_aliases}`` for every bundle in *catalog*.

    Bundles live under Gradle's reserved ``libs.bundles.`` namespace, so
    every key in this map starts with ``"bundles."``. Each bundle is
    registered under both accessor forms — for alias ``compose-ui``::

        "bundles.compose.ui"   → ("androidx-compose-ui", "androidx-compose-material")
        "bundles.composeUi"    → ("androidx-compose-ui", "androidx-compose-material")

    The scanner consults this map only after the library accessor
    lookup fails, so a (hypothetical) library aliased ``bundles-foo``
    still resolves to itself first. In practice Gradle reserves the
    ``bundles`` prefix, so the collision cannot happen for catalogs
    that Gradle accepts.

    RFC-0019 PR #2.
    """
    mapping: dict[str, tuple[str, ...]] = {}
    for bundle in catalog.bundles:
        dotted = "bundles." + _alias_to_accessor(bundle.alias)
        camel = "bundles." + _alias_to_camel(bundle.alias)
        mapping[dotted] = bundle.member_aliases
        mapping[camel] = bundle.member_aliases
    return mapping


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
# Per-module scan helper (RFC-0019 PR #3)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _ModuleScanResult:
    """Outcome of scanning a single ``build.gradle(.kts)``.

    Pure data carrier so the per-module worker can run inside
    ``asyncio.to_thread`` and the main coroutine can aggregate without
    sharing mutable state across tasks.

    Exactly one of two states applies:

    - ``finding is None`` → the file was read successfully; ``credits``
      lists every ``(alias, bucket)`` pair this module should be added
      to (already deduplicated), and ``direct_count`` is the module's
      non-test direct dep count.
    - ``finding is not None`` → the file could not be read; ``credits``
      is empty and ``direct_count`` is 0. The application layer merges
      the finding into ``FreezeReport.health_findings``.
    """

    module_path: str
    credits: tuple[tuple[str, str], ...]
    direct_count: int
    finding: Finding | None


def _scan_module_file(
    module_path: str,
    build_file: Path,
    accessor_map: dict[str, str],
    bundle_accessor_map: dict[str, tuple[str, ...]],
    known_aliases: frozenset[str],
) -> _ModuleScanResult:
    """Read a single ``build.gradle(.kts)`` and extract its catalog usages.

    Pure synchronous worker designed to be dispatched through
    ``asyncio.to_thread``. It receives the two pre-built accessor maps
    and the set of known aliases so it never touches the
    :class:`Catalog` (no shared object across threads).

    Bucket dedup is local to this call: a library referenced both
    directly and via a bundle in the same module is credited once per
    bucket; that decision lives here so the aggregator just appends.
    """
    try:
        text = build_file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        # RFC-0019 PR #1: ``errors="strict"`` (Python's default for
        # ``read_text``) makes corrupt build files surface as a
        # ``MOD-001`` finding instead of the silent U+FFFD substitution
        # the old ``errors="replace"`` produced.
        return _ModuleScanResult(
            module_path=module_path,
            credits=(),
            direct_count=0,
            finding=Finding(
                rule_id="MOD-001",
                severity=Severity.WARNING,
                message=(
                    f"Could not read build file for module `{module_path}`: {type(exc).__name__}"
                ),
                details=f"Path: {build_file}",
            ),
        )

    seen: dict[str, set[str]] = {}
    credits: list[tuple[str, str]] = []
    direct_count = 0

    for m in _DEP_RE.finditer(text):
        config = m.group(1)
        accessor = m.group(2)

        # PR #2 of RFC-0019: library lookup first (fast path), then
        # bundle expansion. Unknown accessors are silently ignored.
        target_aliases: tuple[str, ...]
        direct_alias = accessor_map.get(accessor)
        if direct_alias is not None:
            target_aliases = (direct_alias,)
        else:
            bundle_members = bundle_accessor_map.get(accessor)
            if bundle_members is None:
                continue
            target_aliases = bundle_members

        bucket = _classify_config(config)
        for alias in target_aliases:
            # Bundle pointing at an alias missing from ``[libraries]``
            # is a catalog-health concern (HDX-002), not a scanner crash.
            if alias not in known_aliases:
                continue
            already = seen.get(alias)
            if already is None:
                seen[alias] = {bucket}
            elif bucket in already:
                continue
            else:
                already.add(bucket)
            credits.append((alias, bucket))
            if bucket != "test":
                direct_count += 1

    return _ModuleScanResult(
        module_path=module_path,
        credits=tuple(credits),
        direct_count=direct_count,
        finding=None,
    )


# ---------------------------------------------------------------------------
# GradleModuleScanner
# ---------------------------------------------------------------------------


class GradleModuleScanner:
    """Scans Gradle build files to produce a :class:`~...domain.module_usage.ModuleUsageMap`.

    This is a **static** scanner — it never invokes the Gradle daemon.
    It reads ``build.gradle(.kts)`` files directly using regex-based
    parsing.  Accuracy is high for the common single-line declaration
    patterns; multi-line and programmatic declarations may be missed.

    Concurrency
    -----------
    RFC-0019 PR #3 made :meth:`scan` async. Each module's I/O + regex
    work runs in a worker thread via ``asyncio.to_thread`` and the
    coroutine ``gather``s the results, so a 200-module project no
    longer pays a serialised read for every build file. The public
    contract is the same: callers ``await`` the coroutine (or wrap it
    with ``asyncio.run`` at the CLI entry point).
    """

    async def scan(self, catalog_path: Path, catalog: Catalog) -> ModuleUsageMap | None:
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
            # The settings file is small and read once, but we still go
            # through ``to_thread`` to keep the event loop non-blocking
            # for callers that drive several adapters in parallel.
            settings_text = await asyncio.to_thread(
                settings_file.read_text, encoding="utf-8", errors="replace"
            )
        except OSError:
            return None

        module_paths = _parse_module_paths(settings_text)
        if not module_paths:
            return None

        accessor_map = _build_accessor_map(catalog)
        # RFC-0019 PR #2: a second table maps ``bundles.<form>`` accessors
        # to the bundle's member library aliases. Consulted only when the
        # library lookup misses, so direct ``libs.<lib>`` references keep
        # their existing fast path.
        bundle_accessor_map = _build_bundle_accessor_map(catalog)
        known_aliases = frozenset(lib.alias for lib in catalog.libraries)

        # Resolve build files up-front (cheap stat calls) so the parallel
        # workers receive a ready-to-read path; modules without a build
        # file are skipped here, matching the pre-PR #3 contract that
        # they don't appear in ``modules_scanned``.
        modules_with_files: list[tuple[str, Path]] = []
        for module_path in module_paths:
            build_file = _find_build_file(_module_dir(project_root, module_path))
            if build_file is not None:
                modules_with_files.append((module_path, build_file))

        # Parallel I/O + parse. ``asyncio.to_thread`` dispatches each
        # worker to the default thread pool; ``gather`` waits for all to
        # complete. Results come back in the order they were submitted,
        # so aggregation produces stable ``module_summaries`` ordering
        # after the trailing ``sorted(...)``.
        results: tuple[_ModuleScanResult, ...] = tuple(
            await asyncio.gather(
                *(
                    asyncio.to_thread(
                        _scan_module_file,
                        module_path,
                        build_file,
                        accessor_map,
                        bundle_accessor_map,
                        known_aliases,
                    )
                    for module_path, build_file in modules_with_files
                )
            )
        )

        # Aggregate in the main coroutine (no contention, no shared
        # mutable state across tasks).
        usage: dict[str, dict[str, list[str]]] = {
            lib.alias: {"impl": [], "api": [], "test": []} for lib in catalog.libraries
        }
        module_direct_counts: dict[str, int] = {}
        scan_findings: list[Finding] = []

        for result in results:
            if result.finding is not None:
                scan_findings.append(result.finding)
                continue
            for alias, bucket in result.credits:
                # ``known_aliases`` already filtered orphans in the
                # worker, so this lookup is safe.
                usage[alias][bucket].append(result.module_path)
            module_direct_counts[result.module_path] = result.direct_count

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
            findings=tuple(scan_findings),
        )
