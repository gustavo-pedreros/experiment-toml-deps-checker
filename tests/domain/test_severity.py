"""Unit tests for CommonSeverity and the to_common() mappers (RFC-0016a)."""

from __future__ import annotations

import pytest

from gradle_deps_monitor.domain.advisory import AdvisorySeverity
from gradle_deps_monitor.domain.compliance import ComplianceSeverity
from gradle_deps_monitor.domain.finding import Severity
from gradle_deps_monitor.domain.library_health import LibraryHealthSeverity
from gradle_deps_monitor.domain.severity import CommonSeverity, HasCommonSeverity
from gradle_deps_monitor.domain.toolchain import ToolchainSeverity


class TestCommonSeverity:
    def test_values(self) -> None:
        assert CommonSeverity.ERROR == "error"
        assert CommonSeverity.WARNING == "warning"
        assert CommonSeverity.INFO == "info"
        assert CommonSeverity.SUGGESTION == "suggestion"


# ---------------------------------------------------------------------------
# Catalog health (Severity)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "src,expected",
    [
        (Severity.ERROR, CommonSeverity.ERROR),
        (Severity.WARNING, CommonSeverity.WARNING),
        (Severity.INFO, CommonSeverity.INFO),
        (Severity.SUGGESTION, CommonSeverity.SUGGESTION),
    ],
)
def test_catalog_severity_to_common(src: Severity, expected: CommonSeverity) -> None:
    assert src.to_common() is expected


def test_catalog_severity_covers_all_values() -> None:
    """Every Severity value has a CommonSeverity mapping (no KeyError)."""
    for s in Severity:
        s.to_common()


# ---------------------------------------------------------------------------
# Library health
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "src,expected",
    [
        # HIGH = deprecated/relocated → ERROR (end-of-life)
        (LibraryHealthSeverity.HIGH, CommonSeverity.ERROR),
        # MEDIUM = inactive → WARNING (still works but no new releases)
        (LibraryHealthSeverity.MEDIUM, CommonSeverity.WARNING),
        # LOW = informational
        (LibraryHealthSeverity.LOW, CommonSeverity.INFO),
    ],
)
def test_library_health_severity_to_common(
    src: LibraryHealthSeverity, expected: CommonSeverity
) -> None:
    assert src.to_common() is expected


def test_library_health_severity_covers_all_values() -> None:
    for s in LibraryHealthSeverity:
        s.to_common()


# ---------------------------------------------------------------------------
# Compliance
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "src,expected",
    [
        (ComplianceSeverity.ERROR, CommonSeverity.ERROR),
        (ComplianceSeverity.WARNING, CommonSeverity.WARNING),
        (ComplianceSeverity.INFO, CommonSeverity.INFO),
    ],
)
def test_compliance_severity_to_common(src: ComplianceSeverity, expected: CommonSeverity) -> None:
    assert src.to_common() is expected


def test_compliance_severity_covers_all_values() -> None:
    for s in ComplianceSeverity:
        s.to_common()


# ---------------------------------------------------------------------------
# Toolchain
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "src,expected",
    [
        (ToolchainSeverity.ERROR, CommonSeverity.ERROR),
        (ToolchainSeverity.WARNING, CommonSeverity.WARNING),
        (ToolchainSeverity.INFO, CommonSeverity.INFO),
    ],
)
def test_toolchain_severity_to_common(src: ToolchainSeverity, expected: CommonSeverity) -> None:
    assert src.to_common() is expected


def test_toolchain_severity_covers_all_values() -> None:
    for s in ToolchainSeverity:
        s.to_common()


# ---------------------------------------------------------------------------
# Advisory (CVE)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "src,expected",
    [
        # CRITICAL and HIGH both block releases → ERROR
        (AdvisorySeverity.CRITICAL, CommonSeverity.ERROR),
        (AdvisorySeverity.HIGH, CommonSeverity.ERROR),
        (AdvisorySeverity.MEDIUM, CommonSeverity.WARNING),
        # LOW and UNKNOWN collapse to INFO so they don't out-shout
        # genuinely actionable findings.
        (AdvisorySeverity.LOW, CommonSeverity.INFO),
        (AdvisorySeverity.UNKNOWN, CommonSeverity.INFO),
    ],
)
def test_advisory_severity_to_common(src: AdvisorySeverity, expected: CommonSeverity) -> None:
    assert src.to_common() is expected


def test_advisory_severity_covers_all_values() -> None:
    for s in AdvisorySeverity:
        s.to_common()


# ---------------------------------------------------------------------------
# HasCommonSeverity protocol — structural contract every severity satisfies.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "severity",
    [
        Severity.ERROR,
        LibraryHealthSeverity.HIGH,
        ComplianceSeverity.WARNING,
        ToolchainSeverity.INFO,
        AdvisorySeverity.CRITICAL,
    ],
)
def test_section_severities_satisfy_has_common_severity(severity: object) -> None:
    """Every section enum value is structurally a HasCommonSeverity.

    The Protocol is the type that cross-section consumers (writers, console)
    use to accept any severity without an enum union.
    """
    assert isinstance(severity, HasCommonSeverity)
    # Even though isinstance only checks attribute presence, exercise the
    # method to make sure the runtime invocation succeeds too.
    assert isinstance(severity.to_common(), CommonSeverity)  # type: ignore[attr-defined]


def test_non_severity_object_fails_protocol() -> None:
    """An object without to_common() must not satisfy the protocol."""

    class _Plain:
        pass

    assert not isinstance(_Plain(), HasCommonSeverity)
