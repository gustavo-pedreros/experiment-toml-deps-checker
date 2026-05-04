"""ToolchainCompatibilityChecker — validates toolchain versions against bundled matrices."""

from __future__ import annotations

import re
import tomllib
from importlib import resources
from typing import Any

import yaml

from gradle_deps_monitor.domain.catalog import Catalog
from gradle_deps_monitor.domain.toolchain import ToolchainFinding, ToolchainSeverity

# ---------------------------------------------------------------------------
# Version key tokens (after normalisation: lowercase, separators removed)
# ---------------------------------------------------------------------------
_KOTLIN_TOKENS = {"kotlin", "kotlinversion"}
_AGP_TOKENS = {"agp", "androidgradleplugin", "agpversion"}
_KSP_TOKENS = {"ksp", "kspversion"}
_COMPOSE_COMPILER_TOKENS = {
    "composecompiler",
    "composekotlincompilerextensionversion",
    "composecompilerextensionversion",
}

# Rule identifiers
_RULE_KC = "TOOL-KC-001"  # Kotlin ↔ Compose Compiler
_RULE_KSP = "TOOL-KSP-001"  # Kotlin ↔ KSP
_RULE_AGP = "TOOL-AGP-001"  # AGP ↔ Gradle


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_yaml(filename: str) -> dict[str, Any]:
    """Load a bundled YAML file from the ``data/compatibility/`` package."""
    pkg = resources.files("gradle_deps_monitor.data.compatibility")
    text = (pkg / filename).read_text(encoding="utf-8")
    return yaml.safe_load(text)  # type: ignore[no-any-return]


def _normalize_key(key: str) -> str:
    """Lowercase and remove separators from a TOML version key.

    Examples::

        "kotlinVersion"      → "kotlinversion"
        "android-gradle-plugin" → "androidgradleplugin"
        "ksp-version"        → "kspversion"
    """
    return key.lower().replace("-", "").replace("_", "")


def _version_tuple(version: str) -> tuple[int, ...]:
    """Convert a version string to a tuple of ints for comparison.

    ``"8.11"`` → ``(8, 11)``; ``"8.11.1"`` → ``(8, 11, 1)``
    """
    try:
        return tuple(int(x) for x in version.split("."))
    except ValueError:
        return (0,)


def _find_toolchain_versions(catalog: Catalog) -> dict[str, str]:
    """Extract toolchain-relevant version strings from the catalog TOML.

    Returns a dict with any of the keys ``"kotlin"``, ``"agp"``, ``"ksp"``,
    ``"compose_compiler"`` that could be found. Missing keys are omitted.
    """
    try:
        with open(catalog.source_path, "rb") as fh:
            data = tomllib.load(fh)
    except OSError:
        return {}

    versions: dict[str, Any] = data.get("versions", {})
    result: dict[str, str] = {}

    for key, value in versions.items():
        if not isinstance(value, str):
            continue
        norm = _normalize_key(key)
        if norm in _KOTLIN_TOKENS and "kotlin" not in result:
            result["kotlin"] = value
        elif norm in _AGP_TOKENS and "agp" not in result:
            result["agp"] = value
        elif norm in _KSP_TOKENS and "ksp" not in result:
            result["ksp"] = value
        elif norm in _COMPOSE_COMPILER_TOKENS and "compose_compiler" not in result:
            result["compose_compiler"] = value

    return result


def _find_gradle_version(catalog: Catalog) -> str | None:
    """Extract the Gradle version from the wrapper properties file.

    Looks for ``gradle/wrapper/gradle-wrapper.properties`` relative to the
    catalog file's parent directory (the standard layout).
    """
    wrapper_path = catalog.source_path.parent / "wrapper" / "gradle-wrapper.properties"
    if not wrapper_path.exists():
        return None
    try:
        content = wrapper_path.read_text(encoding="utf-8")
    except OSError:
        return None
    match = re.search(r"gradle-(\d+\.\d+(?:\.\d+)?)-", content)
    return match.group(1) if match else None


# ---------------------------------------------------------------------------
# Checker
# ---------------------------------------------------------------------------


class ToolchainCompatibilityChecker:
    """Validates toolchain version combinations against the bundled matrices.

    Three rules are evaluated:

    * **TOOL-KC-001** — Kotlin ↔ Compose Compiler
    * **TOOL-KSP-001** — Kotlin ↔ KSP
    * **TOOL-AGP-001** — AGP ↔ Gradle (requires a discoverable wrapper file)
    """

    def __init__(self) -> None:
        self._kc_matrix: list[dict[str, str]] = _load_yaml("kotlin-compose.yaml").get(
            "compatibility", []
        )
        self._agp_matrix: list[dict[str, Any]] = _load_yaml("agp-gradle.yaml").get(
            "requirements", []
        )

    def check(self, catalog: Catalog) -> tuple[ToolchainFinding, ...]:
        """Return toolchain compatibility findings for *catalog*."""
        versions = _find_toolchain_versions(catalog)
        gradle_version = _find_gradle_version(catalog)

        findings: list[ToolchainFinding] = []
        findings.extend(self._check_kotlin_compose(versions))
        findings.extend(self._check_kotlin_ksp(versions))
        findings.extend(self._check_agp_gradle(versions, gradle_version))
        return tuple(findings)

    # ------------------------------------------------------------------
    # TOOL-KC-001: Kotlin ↔ Compose Compiler
    # ------------------------------------------------------------------

    def _check_kotlin_compose(self, versions: dict[str, str]) -> list[ToolchainFinding]:
        kotlin = versions.get("kotlin")
        compose = versions.get("compose_compiler")

        if not kotlin or not compose:
            return []

        kotlin_major = _version_tuple(kotlin)[0] if _version_tuple(kotlin) else 0

        if kotlin_major >= 2:
            # Kotlin 2.x: compose compiler version must equal kotlin version.
            if compose == kotlin:
                return []
            return [
                ToolchainFinding(
                    rule_id=_RULE_KC,
                    severity=ToolchainSeverity.ERROR,
                    message=(
                        f"Kotlin {kotlin} requires Compose Compiler {kotlin}, but found {compose}"
                    ),
                    detail=(
                        "Since Kotlin 2.0 the Compose Compiler is bundled with the Kotlin "
                        "compiler plugin. The compose-compiler version must match the Kotlin "
                        "version exactly."
                    ),
                    recommendation=f"Set compose-compiler to {kotlin}.",
                )
            ]

        # Kotlin < 2.0: look up in the matrix.
        expected = next(
            (entry["compose_compiler"] for entry in self._kc_matrix if entry["kotlin"] == kotlin),
            None,
        )
        if expected is None:
            return [
                ToolchainFinding(
                    rule_id=_RULE_KC,
                    severity=ToolchainSeverity.WARNING,
                    message=(
                        f"Kotlin {kotlin} is not in the compatibility matrix — "
                        f"cannot verify Compose Compiler {compose}"
                    ),
                    detail=(
                        "Update the bundled kotlin-compose.yaml matrix or check the official docs."
                    ),
                    recommendation=(
                        "Check https://developer.android.com/jetpack/androidx/releases/compose-kotlin"
                    ),
                )
            ]
        if compose == expected:
            return []
        return [
            ToolchainFinding(
                rule_id=_RULE_KC,
                severity=ToolchainSeverity.ERROR,
                message=(
                    f"Kotlin {kotlin} requires Compose Compiler {expected}, but found {compose}"
                ),
                detail=(
                    "Mismatched versions can cause Compose runtime crashes or compilation errors."
                ),
                recommendation=f"Set compose-compiler to {expected}.",
            )
        ]

    # ------------------------------------------------------------------
    # TOOL-KSP-001: Kotlin ↔ KSP
    # ------------------------------------------------------------------

    def _check_kotlin_ksp(self, versions: dict[str, str]) -> list[ToolchainFinding]:
        kotlin = versions.get("kotlin")
        ksp = versions.get("ksp")

        if not kotlin or not ksp:
            return []

        expected_prefix = f"{kotlin}-"
        if ksp.startswith(expected_prefix):
            return []

        # Determine what the user likely intended.
        ksp_parts = ksp.split("-", 1)
        ksp_kotlin_part = ksp_parts[0] if ksp_parts else ksp
        recommendation = (
            f"Replace the Kotlin prefix of your KSP version with {kotlin}. "
            f'E.g. if ksp = "{ksp}", change it to "{kotlin}-{ksp_parts[1]}" '
            f"(keep the same KSP release number)."
            if len(ksp_parts) == 2
            else f"Use a KSP version that starts with {kotlin}- (e.g. {kotlin}-1.0.29)."
        )

        return [
            ToolchainFinding(
                rule_id=_RULE_KSP,
                severity=ToolchainSeverity.ERROR,
                message=(
                    f"KSP {ksp} does not match Kotlin {kotlin} "
                    f"(expected prefix {expected_prefix!r})"
                ),
                detail=(
                    f"KSP versions are tightly coupled to the Kotlin version. "
                    f"The KSP version must start with the Kotlin version prefix "
                    f"(found Kotlin prefix '{ksp_kotlin_part}', expected '{kotlin}')."
                ),
                recommendation=recommendation,
            )
        ]

    # ------------------------------------------------------------------
    # TOOL-AGP-001: AGP ↔ Gradle
    # ------------------------------------------------------------------

    def _check_agp_gradle(
        self,
        versions: dict[str, str],
        gradle_version: str | None,
    ) -> list[ToolchainFinding]:
        agp = versions.get("agp")
        if not agp or not gradle_version:
            return []

        agp_t = _version_tuple(agp)

        # Find the highest agp_min that is <= detected AGP version.
        applicable = [
            req for req in self._agp_matrix if _version_tuple(str(req["agp_min"])) <= agp_t
        ]
        if not applicable:
            return []

        # Pick the strictest (highest agp_min → latest requirement).
        best = max(applicable, key=lambda r: _version_tuple(str(r["agp_min"])))
        min_gradle = str(best["min_gradle"])
        note: str = (best.get("note") or "").strip()

        if _version_tuple(gradle_version) >= _version_tuple(min_gradle):
            return []

        return [
            ToolchainFinding(
                rule_id=_RULE_AGP,
                severity=ToolchainSeverity.ERROR,
                message=(
                    f"AGP {agp} requires Gradle ≥ {min_gradle}, but wrapper has {gradle_version}"
                ),
                detail=note,
                recommendation=(
                    f"Upgrade the Gradle wrapper to {min_gradle} or higher, "
                    f"or downgrade AGP to a version compatible with Gradle {gradle_version}."
                ),
            )
        ]
