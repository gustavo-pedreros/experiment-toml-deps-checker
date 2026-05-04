"""Unit tests for the advisory domain model."""

from __future__ import annotations

import pytest

from gradle_deps_monitor.domain.advisory import Advisory, AdvisorySeverity, LibraryAdvisory


def _advisory(severity: AdvisorySeverity = AdvisorySeverity.HIGH, ghsa: str = "GHSA-test") -> Advisory:
    return Advisory(
        ghsa_id=ghsa,
        cve_id=None,
        severity=severity,
        summary="Test advisory",
        fixed_version="2.0.0",
        url="https://github.com/advisories/GHSA-test",
        source="github",
    )


def _lib_advisory(*advisories: Advisory) -> LibraryAdvisory:
    return LibraryAdvisory(
        alias="my-lib",
        coordinate="com.example:my-lib",
        version="1.0.0",
        advisories=advisories,
    )


# ---------------------------------------------------------------------------
# Advisory
# ---------------------------------------------------------------------------


class TestAdvisory:
    def test_fields_stored(self) -> None:
        adv = _advisory(AdvisorySeverity.CRITICAL, "GHSA-xxxx")
        assert adv.ghsa_id == "GHSA-xxxx"
        assert adv.severity == AdvisorySeverity.CRITICAL
        assert adv.source == "github"

    def test_cve_id_optional(self) -> None:
        adv = Advisory(
            ghsa_id="GHSA-x",
            cve_id="CVE-2023-1234",
            severity=AdvisorySeverity.HIGH,
            summary="x",
            fixed_version=None,
            url="https://example.com",
            source="github",
        )
        assert adv.cve_id == "CVE-2023-1234"

    def test_fixed_version_optional(self) -> None:
        adv = _advisory()
        assert adv.fixed_version == "2.0.0"

        adv_no_fix = Advisory(
            ghsa_id="GHSA-x",
            cve_id=None,
            severity=AdvisorySeverity.LOW,
            summary="x",
            fixed_version=None,
            url="https://example.com",
            source="github",
        )
        assert adv_no_fix.fixed_version is None

    def test_immutable(self) -> None:
        adv = _advisory()
        with pytest.raises(Exception):
            adv.severity = AdvisorySeverity.LOW  # type: ignore[misc]


# ---------------------------------------------------------------------------
# LibraryAdvisory
# ---------------------------------------------------------------------------


class TestLibraryAdvisory:
    def test_is_vulnerable_false_when_empty(self) -> None:
        la = _lib_advisory()
        assert la.is_vulnerable is False

    def test_is_vulnerable_true_when_advisories(self) -> None:
        la = _lib_advisory(_advisory())
        assert la.is_vulnerable is True

    def test_max_severity_none_when_empty(self) -> None:
        la = _lib_advisory()
        assert la.max_severity is None

    def test_max_severity_single(self) -> None:
        la = _lib_advisory(_advisory(AdvisorySeverity.MEDIUM))
        assert la.max_severity == AdvisorySeverity.MEDIUM

    def test_max_severity_returns_highest(self) -> None:
        la = _lib_advisory(
            _advisory(AdvisorySeverity.LOW),
            _advisory(AdvisorySeverity.CRITICAL),
            _advisory(AdvisorySeverity.MEDIUM),
        )
        assert la.max_severity == AdvisorySeverity.CRITICAL

    def test_has_critical_false(self) -> None:
        la = _lib_advisory(_advisory(AdvisorySeverity.HIGH))
        assert la.has_critical is False

    def test_has_critical_true(self) -> None:
        la = _lib_advisory(_advisory(AdvisorySeverity.CRITICAL))
        assert la.has_critical is True

    def test_has_high_false(self) -> None:
        la = _lib_advisory(_advisory(AdvisorySeverity.LOW))
        assert la.has_high is False

    def test_has_high_true(self) -> None:
        la = _lib_advisory(_advisory(AdvisorySeverity.HIGH))
        assert la.has_high is True

    def test_max_severity_order(self) -> None:
        """CRITICAL > HIGH > MEDIUM > LOW > UNKNOWN."""
        severities = [
            AdvisorySeverity.UNKNOWN,
            AdvisorySeverity.LOW,
            AdvisorySeverity.MEDIUM,
            AdvisorySeverity.HIGH,
            AdvisorySeverity.CRITICAL,
        ]
        for i, sev in enumerate(severities):
            la = _lib_advisory(*[_advisory(s) for s in severities[: i + 1]])
            assert la.max_severity == sev
