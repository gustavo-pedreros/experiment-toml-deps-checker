"""Synthetic Gradle multi-module project generator (RFC-0019 PR #3).

Used by integration + benchmark tests that need a realistic 100-500
module project without committing hundreds of files. The generator
writes a ``settings.gradle.kts`` and a ``build.gradle(.kts)`` per
module into a caller-provided directory (typically a pytest
``tmp_path``).

The output is intentionally varied so the scanner's main code paths
all get exercised at scale:

- ~70 % of modules declare 3-7 catalog libraries via direct
  ``implementation(libs.<dotted>)`` calls.
- ~20 % of modules use ``libs.<camelCase>`` accessors (the KTS
  convention that ``GradleModuleScanner`` PR #1 fixed).
- ~10 % of modules consume a bundle (``libs.bundles.<form>``) so the
  PR #2 attribution path is exercised.
- A small minority use ``api`` / ``testImplementation`` to vary the
  bucket classification.

The catalog itself ships separately as a small TOML fixture; the
generator only needs to know the alias / bundle names to interpolate.

This file is **not a test module** — pytest ignores it because it
matches no collection rule. Tests import :func:`generate` directly.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# Library + bundle pool
# ---------------------------------------------------------------------------

# Picked to span the three code paths: single-word, multi-segment kebab,
# and aliases that produce distinct dotted vs camelCase forms.
_LIBRARY_ALIASES: tuple[str, ...] = (
    "retrofit",
    "okhttp",
    "moshi",
    "kotlin-stdlib",
    "kotlinx-coroutines-core",
    "androidx-core-ktx",
    "androidx-lifecycle-runtime",
    "androidx-compose-ui",
    "androidx-compose-material",
    "androidx-navigation-compose",
    "androidx-room-runtime",
    "androidx-room-ktx",
    "hilt-android",
    "hilt-compiler",
    "timber",
    "coil-compose",
    "leakcanary",
    "junit",
    "mockk",
    "espresso-core",
)

_BUNDLES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("network", ("retrofit", "okhttp", "moshi")),
    (
        "compose-ui",
        (
            "androidx-compose-ui",
            "androidx-compose-material",
            "androidx-navigation-compose",
        ),
    ),
    ("testing", ("junit", "mockk", "espresso-core")),
)


@dataclass(frozen=True)
class GeneratedProject:
    """Return value of :func:`generate` — caller may inspect the layout."""

    root: Path
    settings_file: Path
    module_paths: tuple[str, ...]
    library_aliases: tuple[str, ...]
    bundle_aliases: tuple[str, ...]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _alias_to_camel(alias: str) -> str:
    """Mirror Gradle's camelCase accessor generation (kept local on purpose).

    The scanner has its own copy of this helper; the generator deliberately
    duplicates the algorithm so the test fixture remains independent from
    the implementation it's meant to exercise.
    """
    parts = [p for p in alias.split("-") if p]
    if not parts:
        return alias
    head = parts[0].lower()
    tail = "".join(p[:1].upper() + p[1:].lower() for p in parts[1:])
    return head + tail


def _module_path(index: int) -> str:
    """Map an integer index to a colon-prefixed Gradle module path.

    A small fan-out keeps the directory tree shallow but realistic — every
    20 modules form a "feature" group, matching how real Android projects
    organise their multi-module layouts.
    """
    group = index // 20
    return f":feature{group:02d}:module{index:03d}"


def _module_dir(root: Path, module_path: str) -> Path:
    return root / module_path.lstrip(":").replace(":", "/")


def _render_dep_line(rng: random.Random, alias: str, kind: str) -> str:
    """Pick a configuration + accessor form and render a single dep line."""
    if kind == "test":
        config = rng.choice(("testImplementation", "androidTestImplementation"))
    elif kind == "api":
        config = "api"
    else:
        config = "implementation"

    # ~30 % camelCase to match the prevalence in modern KTS projects.
    accessor = _alias_to_camel(alias) if rng.random() < 0.3 else alias.replace("-", ".").lower()
    return f"    {config}(libs.{accessor})"


def _render_bundle_line(rng: random.Random, bundle_alias: str) -> str:
    """Render a single ``libs.bundles.<form>`` line, dotted or camelCase."""
    if rng.random() < 0.5:
        accessor = bundle_alias.replace("-", ".").lower()
    else:
        accessor = _alias_to_camel(bundle_alias)
    return f"    implementation(libs.bundles.{accessor})"


def _render_build_file(rng: random.Random, module_index: int) -> str:
    """Compose the body of one ``build.gradle.kts``.

    Module index drives the deterministic style choice (KTS vs Groovy is
    decided per module by the caller, not here).
    """
    lines: list[str] = ["dependencies {"]
    n_direct = rng.randint(3, 7)
    for _ in range(n_direct):
        alias = rng.choice(_LIBRARY_ALIASES)
        # ~15 % api, ~15 % test, rest impl.
        roll = rng.random()
        if roll < 0.15:
            kind = "api"
        elif roll < 0.30:
            kind = "test"
        else:
            kind = "impl"
        lines.append(_render_dep_line(rng, alias, kind))

    # ~10 % of modules also pull in a bundle.
    if module_index % 10 == 0:
        bundle_alias, _members = rng.choice(_BUNDLES)
        lines.append(_render_bundle_line(rng, bundle_alias))

    lines.append("}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate(root: Path, n_modules: int = 200, seed: int = 0) -> GeneratedProject:
    """Materialise a synthetic Gradle project under *root*.

    :param root: Target directory. Must already exist (e.g. pytest
        ``tmp_path``). The generator writes ``settings.gradle.kts`` and a
        nested module tree directly under this directory.
    :param n_modules: Number of ``build.gradle.kts`` files to create.
        Defaults to 200 — the lower bound the RFC's benchmark cares about.
    :param seed: PRNG seed so the same call always produces the same tree.
        Helpful when comparing repeated benchmark runs.
    :returns: A :class:`GeneratedProject` describing the layout.

    Writes are sequential and use ``Path.write_text``; for the largest
    sizes the I/O dominates, but generation cost is still small relative
    to a single full scan.
    """
    if n_modules <= 0:
        raise ValueError(f"n_modules must be positive, got {n_modules}")
    rng = random.Random(seed)

    module_paths = tuple(_module_path(i) for i in range(n_modules))

    settings_lines = ['rootProject.name = "large-synthetic"', ""]
    settings_lines.extend(f'include("{p}")' for p in module_paths)
    settings_file = root / "settings.gradle.kts"
    settings_file.write_text("\n".join(settings_lines), encoding="utf-8")

    for i, module_path in enumerate(module_paths):
        m_dir = _module_dir(root, module_path)
        m_dir.mkdir(parents=True, exist_ok=True)
        (m_dir / "build.gradle.kts").write_text(_render_build_file(rng, i), encoding="utf-8")

    return GeneratedProject(
        root=root,
        settings_file=settings_file,
        module_paths=module_paths,
        library_aliases=_LIBRARY_ALIASES,
        bundle_aliases=tuple(b[0] for b in _BUNDLES),
    )


def build_catalog_for(project: GeneratedProject):  # type: ignore[no-untyped-def]
    """Construct a domain :class:`Catalog` matching the generated layout.

    Importing the domain at module top-level would create a test-only
    dependency that linters complain about; defer the import so the
    generator itself stays import-light.
    """
    from gradle_deps_monitor.domain.catalog import Bundle, Catalog, Library
    from gradle_deps_monitor.domain.version import MavenVersion

    libraries = tuple(
        Library(
            alias=alias,
            group="com.example",
            artifact=alias,
            version=MavenVersion("1.0.0"),
        )
        for alias in project.library_aliases
    )
    bundles = tuple(Bundle(alias=alias, member_aliases=members) for alias, members in _BUNDLES)
    return Catalog(
        source_path=project.root / "gradle" / "libs.versions.toml",
        libraries=libraries,
        plugins=(),
        bundles=bundles,
    )
