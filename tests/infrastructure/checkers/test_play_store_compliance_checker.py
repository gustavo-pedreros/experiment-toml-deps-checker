"""Unit tests for PlayStoreComplianceChecker."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from gradle_deps_monitor.domain.catalog import Catalog, Library
from gradle_deps_monitor.domain.compliance import ComplianceSeverity
from gradle_deps_monitor.domain.version import MavenVersion
from gradle_deps_monitor.infrastructure.checkers.play_store_compliance_checker import (
    PlayStoreComplianceChecker,
    _find_sdk_versions,
    _normalize_version_key,
)

# ---------------------------------------------------------------------------
# Fixed reference date so tests are deterministic regardless of when they run.
# 2026-05-04 — all 2024 and 2025 deadlines are in the past.
# ---------------------------------------------------------------------------
_TODAY = date(2026, 5, 4)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_lib(group: str, artifact: str) -> Library:
    return Library(
        alias=f"{group}-{artifact}",
        group=group,
        artifact=artifact,
        version=MavenVersion("1.0.0"),
    )


def _make_catalog(
    *libs: Library,
    source_path: Path = Path("libs.versions.toml"),
) -> Catalog:
    return Catalog(
        source_path=source_path,
        libraries=libs,
        plugins=(),
        bundles=(),
    )


# ---------------------------------------------------------------------------
# _normalize_version_key helper
# ---------------------------------------------------------------------------


class TestNormalizeVersionKey:
    def test_strips_android_prefix(self) -> None:
        assert _normalize_version_key("android-targetSdk") == "targetsdk"

    def test_strips_android_underscore_prefix(self) -> None:
        assert _normalize_version_key("android_targetSdk") == "targetsdk"

    def test_strips_android_no_separator(self) -> None:
        assert _normalize_version_key("androidTargetSdk") == "targetsdk"

    def test_no_prefix(self) -> None:
        assert _normalize_version_key("targetSdk") == "targetsdk"

    def test_removes_hyphens_and_underscores(self) -> None:
        assert _normalize_version_key("target-sdk-version") == "targetsdkversion"

    def test_compile_sdk(self) -> None:
        assert _normalize_version_key("compileSdk") == "compilesdk"

    def test_min_sdk(self) -> None:
        assert _normalize_version_key("minSdk") == "minsdk"


# ---------------------------------------------------------------------------
# _find_sdk_versions helper
# ---------------------------------------------------------------------------


class TestFindSdkVersions:
    def test_detects_target_sdk(self, tmp_path: Path) -> None:
        toml = tmp_path / "libs.versions.toml"
        toml.write_text('[versions]\ntargetSdk = "35"\n')
        catalog = _make_catalog(source_path=toml)
        result = _find_sdk_versions(catalog)
        assert result["targetSdk"] == 35

    def test_detects_android_prefix(self, tmp_path: Path) -> None:
        toml = tmp_path / "libs.versions.toml"
        toml.write_text('[versions]\nandroid-compileSdk = "35"\n')
        catalog = _make_catalog(source_path=toml)
        result = _find_sdk_versions(catalog)
        assert result["compileSdk"] == 35

    def test_detects_min_sdk(self, tmp_path: Path) -> None:
        toml = tmp_path / "libs.versions.toml"
        toml.write_text('[versions]\nminSdk = "24"\n')
        catalog = _make_catalog(source_path=toml)
        result = _find_sdk_versions(catalog)
        assert result["minSdk"] == 24

    def test_ignores_non_integer_values(self, tmp_path: Path) -> None:
        toml = tmp_path / "libs.versions.toml"
        toml.write_text('[versions]\ntargetSdk = "35.0"\n')
        catalog = _make_catalog(source_path=toml)
        result = _find_sdk_versions(catalog)
        assert "targetSdk" not in result

    def test_returns_empty_when_file_missing(self) -> None:
        catalog = _make_catalog(source_path=Path("/nonexistent/libs.versions.toml"))
        result = _find_sdk_versions(catalog)
        assert result == {}

    def test_returns_empty_when_no_sdk_keys(self, tmp_path: Path) -> None:
        toml = tmp_path / "libs.versions.toml"
        toml.write_text('[versions]\nkotlin = "2.0.0"\n')
        catalog = _make_catalog(source_path=toml)
        result = _find_sdk_versions(catalog)
        assert result == {}


# ---------------------------------------------------------------------------
# PlayStoreComplianceChecker — deprecated library detection
# ---------------------------------------------------------------------------


class TestDeprecatedLibraryDetection:
    def _checker(self) -> PlayStoreComplianceChecker:
        return PlayStoreComplianceChecker(reference_date=_TODAY)

    def test_flags_safetynet(self) -> None:
        lib = _make_lib("com.google.android.gms", "play-services-safetynet")
        catalog = _make_catalog(lib)
        findings = self._checker().check(catalog)
        rule_ids = {f.rule_id for f in findings}
        assert "PLAY-DEP-001" in rule_ids

    def test_safetynet_is_error_when_deadline_past(self) -> None:
        lib = _make_lib("com.google.android.gms", "play-services-safetynet")
        catalog = _make_catalog(lib)
        findings = self._checker().check(catalog)
        safetynet = next(f for f in findings if f.rule_id == "PLAY-DEP-001")
        assert safetynet.severity == ComplianceSeverity.ERROR

    def test_safetynet_includes_migration(self) -> None:
        lib = _make_lib("com.google.android.gms", "play-services-safetynet")
        catalog = _make_catalog(lib)
        findings = self._checker().check(catalog)
        safetynet = next(f for f in findings if f.rule_id == "PLAY-DEP-001")
        assert safetynet.migration == "com.google.android.play:integrity"

    def test_flags_gcm(self) -> None:
        lib = _make_lib("com.google.android.gms", "play-services-gcm")
        catalog = _make_catalog(lib)
        findings = self._checker().check(catalog)
        rule_ids = {f.rule_id for f in findings}
        assert "PLAY-DEP-002" in rule_ids

    def test_flags_legacy_crashlytics(self) -> None:
        lib = _make_lib("com.crashlytics.sdk.android", "crashlytics")
        catalog = _make_catalog(lib)
        findings = self._checker().check(catalog)
        rule_ids = {f.rule_id for f in findings}
        assert "PLAY-DEP-006" in rule_ids

    def test_no_findings_for_clean_catalog(self) -> None:
        lib = _make_lib("com.squareup.okhttp3", "okhttp")
        catalog = _make_catalog(lib)
        findings = self._checker().check(catalog)
        # Only deprecated lib / SDK checks — clean catalog should have no dep findings.
        dep_findings = [f for f in findings if f.rule_id.startswith("PLAY-DEP")]
        assert dep_findings == []

    def test_multiple_deprecated_libs_all_flagged(self) -> None:
        libs = (
            _make_lib("com.google.android.gms", "play-services-safetynet"),
            _make_lib("com.google.android.gms", "play-services-gcm"),
        )
        catalog = _make_catalog(*libs)
        findings = self._checker().check(catalog)
        rule_ids = {f.rule_id for f in findings}
        assert "PLAY-DEP-001" in rule_ids
        assert "PLAY-DEP-002" in rule_ids

    def test_empty_catalog_no_findings(self) -> None:
        catalog = _make_catalog()
        findings = self._checker().check(catalog)
        assert findings == ()

    def test_finding_with_no_deadline_is_error(self) -> None:
        """firebase-core has no hard deadline → treated as ERROR (no migration path)."""
        lib = _make_lib("com.google.firebase", "firebase-core")
        catalog = _make_catalog(lib)
        findings = self._checker().check(catalog)
        core_finding = next((f for f in findings if f.rule_id == "PLAY-DEP-005"), None)
        assert core_finding is not None
        assert core_finding.severity == ComplianceSeverity.ERROR

    # ------------------------------------------------------------------
    # RFC-0015: per-library attribution
    # ------------------------------------------------------------------

    def test_safetynet_finding_carries_alias(self) -> None:
        """Library-specific findings populate alias and coordinate."""
        lib = Library(
            alias="safetynet",
            group="com.google.android.gms",
            artifact="play-services-safetynet",
            version=MavenVersion("1.0.0"),
        )
        catalog = _make_catalog(lib)
        findings = self._checker().check(catalog)
        safetynet = next(f for f in findings if f.rule_id == "PLAY-DEP-001")
        assert safetynet.alias == "safetynet"
        assert safetynet.coordinate == "com.google.android.gms:play-services-safetynet"

    def test_alias_uses_catalog_alias_not_artifact(self) -> None:
        """The alias field comes from the TOML alias, not the Maven artifactId."""
        lib = Library(
            alias="play-svc-safety",  # custom catalog alias
            group="com.google.android.gms",
            artifact="play-services-safetynet",
            version=MavenVersion("1.0.0"),
        )
        catalog = _make_catalog(lib)
        findings = self._checker().check(catalog)
        safetynet = next(f for f in findings if f.rule_id == "PLAY-DEP-001")
        assert safetynet.alias == "play-svc-safety"

    def test_first_alias_wins_when_coordinate_duplicated(self) -> None:
        """A coordinate listed under multiple aliases attributes to the first one."""
        first = Library(
            alias="safetynet-a",
            group="com.google.android.gms",
            artifact="play-services-safetynet",
            version=MavenVersion("1.0.0"),
        )
        second = Library(
            alias="safetynet-b",
            group="com.google.android.gms",
            artifact="play-services-safetynet",
            version=MavenVersion("1.0.0"),
        )
        catalog = _make_catalog(first, second)
        findings = self._checker().check(catalog)
        safetynet = next(f for f in findings if f.rule_id == "PLAY-DEP-001")
        assert safetynet.alias == "safetynet-a"


# ---------------------------------------------------------------------------
# PlayStoreComplianceChecker — SDK requirement checks
# ---------------------------------------------------------------------------


class TestSdkRequirementChecks:
    def _checker(self, today: date = _TODAY) -> PlayStoreComplianceChecker:
        return PlayStoreComplianceChecker(reference_date=today)

    def test_no_sdk_findings_when_target_sdk_not_detected(self, tmp_path: Path) -> None:
        toml = tmp_path / "libs.versions.toml"
        toml.write_text('[versions]\nkotlin = "2.0.0"\n')
        catalog = _make_catalog(source_path=toml)
        findings = self._checker().check(catalog)
        sdk_findings = [f for f in findings if f.rule_id.startswith("PLAY-SDK")]
        assert sdk_findings == []

    def test_error_when_target_sdk_below_required(self, tmp_path: Path) -> None:
        toml = tmp_path / "libs.versions.toml"
        toml.write_text('[versions]\ntargetSdk = "33"\n')
        catalog = _make_catalog(source_path=toml)
        findings = self._checker().check(catalog)
        sdk_findings = [f for f in findings if f.rule_id.startswith("PLAY-SDK")]
        assert len(sdk_findings) == 1
        assert sdk_findings[0].severity == ComplianceSeverity.ERROR

    def test_no_sdk_finding_when_compliant(self, tmp_path: Path) -> None:
        toml = tmp_path / "libs.versions.toml"
        toml.write_text('[versions]\ntargetSdk = "35"\n')
        catalog = _make_catalog(source_path=toml)
        findings = self._checker().check(catalog)
        sdk_findings = [f for f in findings if f.rule_id.startswith("PLAY-SDK")]
        assert sdk_findings == []

    def test_no_sdk_findings_when_no_past_deadlines(self, tmp_path: Path) -> None:
        """If reference date is before all deadlines, no SDK requirements apply."""
        early_date = date(2023, 1, 1)
        toml = tmp_path / "libs.versions.toml"
        toml.write_text('[versions]\ntargetSdk = "33"\n')
        catalog = _make_catalog(source_path=toml)
        findings = self._checker(today=early_date).check(catalog)
        sdk_findings = [f for f in findings if f.rule_id.startswith("PLAY-SDK")]
        assert sdk_findings == []

    def test_sdk_finding_message_includes_api_levels(self, tmp_path: Path) -> None:
        toml = tmp_path / "libs.versions.toml"
        toml.write_text('[versions]\ntargetSdk = "33"\n')
        catalog = _make_catalog(source_path=toml)
        findings = self._checker().check(catalog)
        sdk_findings = [f for f in findings if f.rule_id.startswith("PLAY-SDK")]
        assert "33" in sdk_findings[0].message
        assert "35" in sdk_findings[0].message

    def test_sdk_finding_has_no_alias(self, tmp_path: Path) -> None:
        """RFC-0015: catalog-level findings keep alias/coordinate as None."""
        toml = tmp_path / "libs.versions.toml"
        toml.write_text('[versions]\ntargetSdk = "33"\n')
        catalog = _make_catalog(source_path=toml)
        findings = self._checker().check(catalog)
        sdk_findings = [f for f in findings if f.rule_id.startswith("PLAY-SDK")]
        assert sdk_findings[0].alias is None
        assert sdk_findings[0].coordinate is None


# ---------------------------------------------------------------------------
# Severity deadline mapping
# ---------------------------------------------------------------------------


class TestDeadlineSeverityMapping:
    def test_past_deadline_is_error(self) -> None:
        checker = PlayStoreComplianceChecker(reference_date=date(2026, 5, 4))
        assert checker._deadline_severity("2025-01-01") == ComplianceSeverity.ERROR

    def test_today_deadline_is_error(self) -> None:
        today = date(2026, 5, 4)
        checker = PlayStoreComplianceChecker(reference_date=today)
        assert checker._deadline_severity("2026-05-04") == ComplianceSeverity.ERROR

    def test_near_deadline_is_warning(self) -> None:
        checker = PlayStoreComplianceChecker(reference_date=date(2026, 5, 4))
        # 90 days from now — within 180-day window
        assert checker._deadline_severity("2026-08-02") == ComplianceSeverity.WARNING

    def test_far_deadline_is_info(self) -> None:
        checker = PlayStoreComplianceChecker(reference_date=date(2026, 5, 4))
        # 200 days from now — beyond 180-day window
        assert checker._deadline_severity("2026-11-20") == ComplianceSeverity.INFO

    def test_null_deadline_is_error(self) -> None:
        checker = PlayStoreComplianceChecker(reference_date=date(2026, 5, 4))
        assert checker._deadline_severity(None) == ComplianceSeverity.ERROR
