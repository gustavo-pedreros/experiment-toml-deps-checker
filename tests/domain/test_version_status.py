"""Unit tests for the version-status domain model (RFC-0013)."""

from __future__ import annotations

import dataclasses

import pytest

from gradle_deps_monitor.domain.version import MavenVersion
from gradle_deps_monitor.domain.version_status import (
    LibraryVersionStatus,
    VersionDrift,
    compute_drift,
    major_delta,
)


def _mv(raw: str) -> MavenVersion:
    return MavenVersion(raw)


# ---------------------------------------------------------------------------
# compute_drift
# ---------------------------------------------------------------------------


class TestComputeDriftNone:
    def test_equal_versions(self) -> None:
        assert compute_drift(_mv("1.2.3"), _mv("1.2.3")) == VersionDrift.NONE

    def test_pinned_ahead_of_latest(self) -> None:
        assert compute_drift(_mv("2.0.0"), _mv("1.5.0")) == VersionDrift.NONE

    def test_short_form_equal(self) -> None:
        # 1.0 vs 1 — both normalise to (1, 0, 0)
        assert compute_drift(_mv("1.0"), _mv("1")) == VersionDrift.NONE


class TestComputeDriftPatch:
    def test_patch_behind(self) -> None:
        assert compute_drift(_mv("1.2.3"), _mv("1.2.4")) == VersionDrift.PATCH

    def test_far_patch_behind(self) -> None:
        assert compute_drift(_mv("1.2.0"), _mv("1.2.99")) == VersionDrift.PATCH


class TestComputeDriftMinor:
    def test_minor_behind(self) -> None:
        assert compute_drift(_mv("1.2.3"), _mv("1.3.0")) == VersionDrift.MINOR

    def test_minor_with_higher_patch(self) -> None:
        # Latest minor is higher even though patch is lower
        assert compute_drift(_mv("1.2.99"), _mv("1.3.0")) == VersionDrift.MINOR


class TestComputeDriftMajor:
    def test_major_behind(self) -> None:
        assert compute_drift(_mv("1.2.3"), _mv("2.0.0")) == VersionDrift.MAJOR

    def test_far_major_behind(self) -> None:
        assert compute_drift(_mv("1.0.0"), _mv("5.0.0")) == VersionDrift.MAJOR


class TestComputeDriftUnknown:
    def test_no_latest(self) -> None:
        assert compute_drift(_mv("1.2.3"), None) == VersionDrift.UNKNOWN

    def test_unparseable_pinned(self) -> None:
        assert compute_drift(_mv("alpha"), _mv("1.2.3")) == VersionDrift.UNKNOWN

    def test_unparseable_latest(self) -> None:
        assert compute_drift(_mv("1.2.3"), _mv("alpha")) == VersionDrift.UNKNOWN


class TestComputeDriftQualifiers:
    """Real-world Android versions with qualifiers."""

    def test_alpha_pinned_stable_latest(self) -> None:
        # 1.2.3-alpha vs 1.2.4 → patch behind (qualifiers ignored)
        assert compute_drift(_mv("1.2.3-alpha"), _mv("1.2.4")) == VersionDrift.PATCH

    def test_rc_versions(self) -> None:
        # 1.0.0-rc01 vs 1.0.0-rc02: numeric prefix is the same, treated as NONE
        assert compute_drift(_mv("1.0.0-rc01"), _mv("1.0.0-rc02")) == VersionDrift.NONE

    def test_androidx_compose_style(self) -> None:
        # androidx artifacts often look like 1.7.0-beta02 → 1.8.0
        assert compute_drift(_mv("1.7.0-beta02"), _mv("1.8.0")) == VersionDrift.MINOR


# ---------------------------------------------------------------------------
# major_delta
# ---------------------------------------------------------------------------


class TestMajorDelta:
    def test_no_latest_returns_zero(self) -> None:
        assert major_delta(_mv("1.2.3"), None) == 0

    def test_one_behind(self) -> None:
        assert major_delta(_mv("1.2.3"), _mv("2.0.0")) == 1

    def test_three_behind(self) -> None:
        assert major_delta(_mv("1.0.0"), _mv("4.0.0")) == 3

    def test_pinned_ahead_returns_zero(self) -> None:
        assert major_delta(_mv("3.0.0"), _mv("2.5.0")) == 0

    def test_unparseable_returns_zero(self) -> None:
        assert major_delta(_mv("alpha"), _mv("1.0.0")) == 0


# ---------------------------------------------------------------------------
# LibraryVersionStatus
# ---------------------------------------------------------------------------


class TestLibraryVersionStatus:
    def test_construction(self) -> None:
        status = LibraryVersionStatus(
            alias="retrofit",
            coordinate="com.squareup.retrofit2:retrofit",
            pinned=_mv("2.9.0"),
            latest=_mv("2.11.0"),
            drift=VersionDrift.MINOR,
        )
        assert status.alias == "retrofit"
        assert status.drift == VersionDrift.MINOR

    def test_frozen(self) -> None:
        status = LibraryVersionStatus(
            alias="x",
            coordinate="a:b",
            pinned=_mv("1.0"),
            latest=None,
            drift=VersionDrift.UNKNOWN,
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            status.alias = "y"  # type: ignore[misc]
