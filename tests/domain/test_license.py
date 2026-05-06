"""Unit tests for the license domain model (RFC-0009)."""

from __future__ import annotations

from gradle_deps_monitor.domain.license import LicenseAudit, LicenseFinding, LicenseTier

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _finding(
    alias: str = "lib",
    tier: LicenseTier = LicenseTier.UNKNOWN,
) -> LicenseFinding:
    return LicenseFinding(
        alias=alias,
        coordinate=f"com.example:{alias}",
        version="1.0.0",
        license_name=None,
        license_url=None,
        tier=tier,
    )


# ---------------------------------------------------------------------------
# LicenseTier
# ---------------------------------------------------------------------------


class TestLicenseTier:
    def test_values_are_strings(self) -> None:
        assert LicenseTier.PERMISSIVE.value == "permissive"
        assert LicenseTier.WEAK_COPYLEFT.value == "weak_copyleft"
        assert LicenseTier.STRONG_COPYLEFT.value == "strong_copyleft"
        assert LicenseTier.UNKNOWN.value == "unknown"

    def test_str_subclass(self) -> None:
        assert LicenseTier.PERMISSIVE == "permissive"


# ---------------------------------------------------------------------------
# LicenseFinding
# ---------------------------------------------------------------------------


class TestLicenseFinding:
    def test_construction(self) -> None:
        f = LicenseFinding(
            alias="retrofit",
            coordinate="com.squareup.retrofit2:retrofit",
            version="2.9.0",
            license_name="Apache 2.0",
            license_url="https://www.apache.org/licenses/LICENSE-2.0",
            tier=LicenseTier.PERMISSIVE,
        )
        assert f.alias == "retrofit"
        assert f.tier == LicenseTier.PERMISSIVE
        assert f.license_name == "Apache 2.0"

    def test_optional_fields_none(self) -> None:
        f = _finding(alias="mystery")
        assert f.license_name is None
        assert f.license_url is None
        assert f.tier == LicenseTier.UNKNOWN

    def test_frozen(self) -> None:
        import dataclasses

        import pytest

        f = _finding()
        with pytest.raises(dataclasses.FrozenInstanceError):
            f.alias = "changed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# LicenseAudit
# ---------------------------------------------------------------------------


class TestLicenseAuditCounts:
    def test_empty_findings_all_permissive(self) -> None:
        audit = LicenseAudit(findings=(), libraries_audited=10)
        assert audit.permissive_count == 10
        assert audit.flagged_count == 0

    def test_some_flagged(self) -> None:
        audit = LicenseAudit(
            findings=(_finding(tier=LicenseTier.STRONG_COPYLEFT),),
            libraries_audited=5,
        )
        assert audit.flagged_count == 1
        assert audit.permissive_count == 4

    def test_all_flagged(self) -> None:
        findings = tuple(_finding(tier=LicenseTier.UNKNOWN) for _ in range(3))
        audit = LicenseAudit(findings=findings, libraries_audited=3)
        assert audit.permissive_count == 0
        assert audit.flagged_count == 3


class TestLicenseAuditProperties:
    def test_has_violations_strong_copyleft(self) -> None:
        audit = LicenseAudit(
            findings=(_finding(tier=LicenseTier.STRONG_COPYLEFT),),
            libraries_audited=1,
        )
        assert audit.has_violations is True
        assert audit.has_warnings is False

    def test_has_warnings_weak_copyleft(self) -> None:
        audit = LicenseAudit(
            findings=(_finding(tier=LicenseTier.WEAK_COPYLEFT),),
            libraries_audited=1,
        )
        assert audit.has_violations is False
        assert audit.has_warnings is True

    def test_has_warnings_unknown(self) -> None:
        audit = LicenseAudit(
            findings=(_finding(tier=LicenseTier.UNKNOWN),),
            libraries_audited=1,
        )
        assert audit.has_warnings is True

    def test_no_violations_no_warnings_all_permissive(self) -> None:
        audit = LicenseAudit(findings=(), libraries_audited=50)
        assert audit.has_violations is False
        assert audit.has_warnings is False

    def test_mixed_findings(self) -> None:
        audit = LicenseAudit(
            findings=(
                _finding(alias="a", tier=LicenseTier.STRONG_COPYLEFT),
                _finding(alias="b", tier=LicenseTier.WEAK_COPYLEFT),
            ),
            libraries_audited=10,
        )
        assert audit.has_violations is True
        assert audit.has_warnings is True
        assert audit.flagged_count == 2
        assert audit.permissive_count == 8
