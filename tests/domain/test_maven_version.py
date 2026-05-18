"""Unit tests for MavenVersion and Stability."""

import pytest

from gradle_deps_monitor.domain.version import MavenVersion, Stability


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # Stable — pure numeric, major >= 1
        ("1.0.0", Stability.STABLE),
        ("2.0.0", Stability.STABLE),
        ("1.9.24", Stability.STABLE),
        ("33.0.0", Stability.STABLE),
        ("8.2.1", Stability.STABLE),
        ("1.2.3.4", Stability.STABLE),
        # PRE_1_0 — naked 0.x.y per SemVer §4 (RFC-0026)
        ("0.0.0", Stability.PRE_1_0),
        ("0.1.0", Stability.PRE_1_0),
        ("0.5.4", Stability.PRE_1_0),
        ("0.10.99", Stability.PRE_1_0),
        # Suffix wins — 0.x.y with qualifier classifies by qualifier
        ("0.5.0-alpha01", Stability.ALPHA),
        ("0.1.0-rc02", Stability.RC),
        ("0.0.0-SNAPSHOT", Stability.SNAPSHOT),
        # Alpha — AndroidX / Kotlin style
        ("2.0.0-alpha01", Stability.ALPHA),
        ("33.0.0-alpha05", Stability.ALPHA),
        ("1.9.0-Alpha1", Stability.ALPHA),
        # Beta
        ("1.9.0-beta01", Stability.BETA),
        ("2.0.0-Beta02", Stability.BETA),
        # RC
        ("2.0.0-RC1", Stability.RC),
        ("8.3.0-rc02", Stability.RC),
        ("1.0.0-RC", Stability.RC),
        # Dev
        ("1.0.0-dev01", Stability.DEV),
        ("2.1.0-dev", Stability.DEV),
        # Snapshot
        ("1.0.0-SNAPSHOT", Stability.SNAPSHOT),
        ("2.0.0-snapshot", Stability.SNAPSHOT),
        # Unknown — non-numeric, no recognisable label
        ("latest.release", Stability.UNKNOWN),
        ("+", Stability.UNKNOWN),
    ],
)
def test_stability_detection(raw: str, expected: Stability) -> None:
    assert MavenVersion(raw).stability == expected


def test_is_stable_true_for_stable_version() -> None:
    assert MavenVersion("1.9.24").is_stable is True


def test_is_stable_false_for_alpha() -> None:
    assert MavenVersion("2.0.0-alpha01").is_stable is False


def test_is_prerelease_true_for_rc() -> None:
    assert MavenVersion("8.3.0-rc02").is_prerelease is True


def test_is_prerelease_false_for_stable() -> None:
    assert MavenVersion("1.0.0").is_prerelease is False


def test_is_prerelease_false_for_unknown() -> None:
    assert MavenVersion("latest.release").is_prerelease is False


def test_is_stable_false_for_pre_1_0() -> None:
    """RFC-0026: ``0.x.y`` libraries are not stable per SemVer §4."""
    assert MavenVersion("0.5.0").is_stable is False


def test_is_prerelease_false_for_pre_1_0() -> None:
    """RFC-0026: PRE_1_0 is a separate axis from suffix-tagged prereleases."""
    assert MavenVersion("0.5.0").is_prerelease is False


def test_str_returns_raw() -> None:
    assert str(MavenVersion("1.9.24")) == "1.9.24"


def test_equality_is_value_based() -> None:
    assert MavenVersion("1.0.0") == MavenVersion("1.0.0")
    assert MavenVersion("1.0.0") != MavenVersion("2.0.0")


def test_hashable() -> None:
    versions = {MavenVersion("1.0.0"), MavenVersion("1.0.0"), MavenVersion("2.0.0")}
    assert len(versions) == 2
