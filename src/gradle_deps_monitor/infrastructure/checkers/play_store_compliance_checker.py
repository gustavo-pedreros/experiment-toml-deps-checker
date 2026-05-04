"""PlayStoreComplianceChecker — checks catalogs against the bundled Play Store KB."""

from __future__ import annotations

import tomllib
from datetime import date
from importlib import resources
from typing import Any

import yaml

from gradle_deps_monitor.domain.catalog import Catalog
from gradle_deps_monitor.domain.compliance import ComplianceFinding, ComplianceSeverity

# Version keys in [versions] that we interpret as targetSdk / compileSdk / minSdk.
# Normalisation: lowercase → strip "android" prefix → remove separators.
_TARGET_SDK_TOKENS = {"targetsdk"}
_COMPILE_SDK_TOKENS = {"compilesdk"}
_MIN_SDK_TOKENS = {"minsdk"}

# Keys in the YAML deprecated_libraries entries.
_FIELD_COORDINATE = "coordinate"
_FIELD_RULE_ID = "rule_id"
_FIELD_MESSAGE = "message"
_FIELD_DETAIL = "detail"
_FIELD_DEADLINE = "deadline"
_FIELD_MIGRATION = "migration"


def _load_kb() -> dict[str, Any]:
    """Load the bundled Play Store compliance knowledge base."""
    pkg = resources.files("gradle_deps_monitor.data")
    text = (pkg / "play_store_compliance.yaml").read_text(encoding="utf-8")
    return yaml.safe_load(text)  # type: ignore[no-any-return]


def _normalize_version_key(key: str) -> str:
    """Normalise a TOML version key for SDK detection.

    Strips common Android prefixes, removes separators, lowercases.
    Examples:
    - ``"android-targetSdk"`` → ``"targetsdk"``
    - ``"compileSdkVersion"`` → ``"compilesdkversion"``
    """
    k = key.lower()
    for prefix in ("android-", "android_", "android"):
        if k.startswith(prefix):
            k = k[len(prefix) :]
            break
    return k.replace("-", "").replace("_", "")


def _find_sdk_versions(catalog: Catalog) -> dict[str, int]:
    """Try to detect targetSdk / compileSdk / minSdk from the TOML [versions] section.

    Returns a dict with any of the keys ``"targetSdk"``, ``"compileSdk"``,
    ``"minSdk"`` that could be parsed as integers.  Missing keys are omitted.
    """
    try:
        with open(catalog.source_path, "rb") as fh:
            data = tomllib.load(fh)
    except (OSError, Exception):
        return {}

    versions: dict[str, str] = data.get("versions", {})
    result: dict[str, int] = {}

    for key, value in versions.items():
        norm = _normalize_version_key(key)
        try:
            int_val = int(value)
        except (ValueError, TypeError):
            continue

        if norm in {"targetsdk", "targetsdkversion"}:
            result.setdefault("targetSdk", int_val)
        elif norm in {"compilesdk", "compilesdkversion"}:
            result.setdefault("compileSdk", int_val)
        elif norm in {"minsdk", "minsdkversion"}:
            result.setdefault("minSdk", int_val)

    return result


class PlayStoreComplianceChecker:
    """Checks a Gradle Version Catalog against the bundled Play Store KB.

    Two categories of checks are performed:

    1. **Deprecated library detection** — any library whose ``group:artifact``
       coordinate matches a known deprecated entry is flagged.
    2. **Target SDK level** — if ``targetSdk`` can be auto-detected from the
       TOML ``[versions]`` section, it is compared against Google's published
       requirements for the given *reference_date*.

    :param reference_date: Date used to evaluate deadline severity.  Defaults
        to today.  Override in tests to produce deterministic output.
    """

    def __init__(self, reference_date: date | None = None) -> None:
        self._today = reference_date or date.today()
        self._kb = _load_kb()

    def check(self, catalog: Catalog) -> tuple[ComplianceFinding, ...]:
        """Return compliance findings for *catalog*."""
        findings: list[ComplianceFinding] = []
        findings.extend(self._check_deprecated_libraries(catalog))
        findings.extend(self._check_sdk_requirements(catalog))
        return tuple(findings)

    # ------------------------------------------------------------------
    # Deprecated library checks
    # ------------------------------------------------------------------

    def _check_deprecated_libraries(self, catalog: Catalog) -> list[ComplianceFinding]:
        catalog_coords = {f"{lib.group}:{lib.artifact}" for lib in catalog.libraries}
        findings: list[ComplianceFinding] = []

        for entry in self._kb.get("deprecated_libraries", []):
            coordinate: str = entry[_FIELD_COORDINATE]
            if coordinate not in catalog_coords:
                continue

            deadline_str: str | None = entry.get(_FIELD_DEADLINE)
            severity = self._deadline_severity(deadline_str)
            detail: str = (entry.get(_FIELD_DETAIL) or "").strip()

            findings.append(
                ComplianceFinding(
                    rule_id=entry[_FIELD_RULE_ID],
                    severity=severity,
                    message=entry[_FIELD_MESSAGE],
                    detail=detail,
                    deadline=deadline_str,
                    migration=entry.get(_FIELD_MIGRATION),
                )
            )

        return findings

    # ------------------------------------------------------------------
    # SDK requirement checks
    # ------------------------------------------------------------------

    def _check_sdk_requirements(self, catalog: Catalog) -> list[ComplianceFinding]:
        sdk_versions = _find_sdk_versions(catalog)
        target_sdk = sdk_versions.get("targetSdk")
        if target_sdk is None:
            return []

        findings: list[ComplianceFinding] = []

        # Find the strictest requirement that is currently in force
        # (deadline <= today, applies_to existing_apps).
        applicable = [
            req
            for req in self._kb.get("sdk_requirements", [])
            if req.get("applies_to") == "existing_apps"
            and date.fromisoformat(req["deadline"]) <= self._today
        ]
        if not applicable:
            return []

        required_sdk = max(req["target_sdk"] for req in applicable)
        if target_sdk >= required_sdk:
            return findings

        # Find the specific requirement that explains the violation.
        violating = next(req for req in applicable if req["target_sdk"] == required_sdk)
        note: str = (violating.get("note") or "").strip()
        findings.append(
            ComplianceFinding(
                rule_id=violating["rule_id"],
                severity=ComplianceSeverity.ERROR,
                message=(f"targetSdk {target_sdk} is below the required API {required_sdk}"),
                detail=note,
                deadline=violating["deadline"],
                migration=None,
            )
        )
        return findings

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _deadline_severity(self, deadline_str: str | None) -> ComplianceSeverity:
        """Map a deadline string to a :class:`ComplianceSeverity`.

        - Past deadline → ERROR
        - Within 180 days → WARNING
        - No deadline → ERROR (deprecated with no transition path is a blocker)
        """
        if deadline_str is None:
            return ComplianceSeverity.ERROR
        deadline = date.fromisoformat(deadline_str)
        if deadline <= self._today:
            return ComplianceSeverity.ERROR
        days_remaining = (deadline - self._today).days
        if days_remaining <= 180:
            return ComplianceSeverity.WARNING
        return ComplianceSeverity.INFO
