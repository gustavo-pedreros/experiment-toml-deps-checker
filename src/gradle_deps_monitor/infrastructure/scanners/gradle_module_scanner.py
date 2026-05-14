"""GradleModuleScanner — static parser for Gradle build files (RFC-0007 / RFC-0019).

Pipeline
--------
1. Walk up from *catalog_path* to find ``settings.gradle(.kts)``.
2. Parse ``include(...)`` calls to enumerate module paths.
3. For each module, locate ``build.gradle(.kts)`` and extract dependency
   declarations that reference ``libs.<accessor>``.
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

import re
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
    """Return the dotted accessor form for *alias* (``-`` → ``.``, lowercased).

    Kept under the historical name so PR #2/#3 follow-ups (and existing
    unit tests) keep working; ``_alias_to_camel`` is the camelCase
    sibling introduced by RFC-0019 PR #1.
    """
    return alias.replace("-", ".").lower()


def _alias_to_camel(alias: str) -> str:
    """Return the camelCase accessor form for *alias*.

    The first segment is lowercased; every subsequent segment is
    title-cased and concatenated::

        "androidx-core-ktx" → "androidxCoreKtx"
        "retrofit"          → "retrofit"
        "okhttp"            → "okhttp"

    Empty segments (from leading / trailing / consecutive ``-``) are
    dropped, matching Gradle's behaviour for malformed aliases.
    """
    parts = [p for p in alias.split("-") if p]
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
        # RFC-0019 PR #2: a second table maps ``bundles.<form>`` accessors
        # to the bundle's member library aliases. Consulted only when the
        # library lookup misses, so direct ``libs.<lib>`` references keep
        # their existing fast path.
        bundle_accessor_map = _build_bundle_accessor_map(catalog)

        # alias → {"impl": [...], "api": [...], "test": [...]}
        usage: dict[str, dict[str, list[str]]] = {
            lib.alias: {"impl": [], "api": [], "test": []} for lib in catalog.libraries
        }
        module_direct_counts: dict[str, int] = {}
        scan_findings: list[Finding] = []

        for module_path in module_paths:
            module_dir = _module_dir(project_root, module_path)
            build_file = _find_build_file(module_dir)
            if build_file is None:
                continue

            # RFC-0019 PR #1: ``errors="strict"`` lets us catch corrupt
            # build files explicitly. Pre-PR #1 the read used
            # ``errors="replace"`` and substituted U+FFFD silently, which
            # masked legitimate corruption and produced false-zero usage
            # numbers for the affected module.
            try:
                text = build_file.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                scan_findings.append(
                    Finding(
                        rule_id="MOD-001",
                        severity=Severity.WARNING,
                        message=(
                            f"Could not read build file for module `{module_path}`: "
                            f"{type(exc).__name__}"
                        ),
                        details=f"Path: {build_file}",
                    )
                )
                continue

            direct_count = 0

            for m in _DEP_RE.finditer(text):
                config = m.group(1)
                # PR #1 of RFC-0019: look up the accessor verbatim. The
                # previous ``.lower()`` discarded the case information
                # that distinguishes ``libs.androidxCoreKtx`` (camelCase)
                # from ``libs.androidx.core.ktx`` (dotted). The dotted
                # form is still all-lowercase by construction, so this
                # is backward-compatible.
                accessor = m.group(2)

                # PR #2 of RFC-0019: resolve the accessor to one or more
                # library aliases. A direct ``libs.<lib>`` hit produces a
                # single-element tuple; a ``libs.bundles.<name>`` hit
                # expands to every member of the bundle. Unknown
                # accessors are silently ignored (could be a stray
                # ``libs.versions.kotlin`` reference, for example).
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
                    # A bundle is free to list an alias that no longer
                    # exists in the catalog (catalog-health rule
                    # ``HDX-002`` flags it separately). Skip silently so
                    # we don't ``KeyError`` mid-scan.
                    buckets = usage.get(alias)
                    if buckets is None:
                        continue
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
            findings=tuple(scan_findings),
        )
