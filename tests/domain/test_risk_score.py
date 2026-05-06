"""Unit tests for the risk score domain model (RFC-0008)."""

from __future__ import annotations

import pytest

from gradle_deps_monitor.domain.risk_score import (
    DimensionScore,
    LibraryRiskScore,
    RiskLevel,
    RiskScoreReport,
    RiskThresholds,
    RiskWeights,
)

# ---------------------------------------------------------------------------
# RiskWeights
# ---------------------------------------------------------------------------


class TestRiskWeights:
    def test_defaults_sum_to_100(self) -> None:
        w = RiskWeights()
        assert (
            w.outdatedness + w.cve + w.abandonment + w.blast_radius + w.compliance + w.license
            == 100
        )

    def test_custom_valid(self) -> None:
        w = RiskWeights(
            outdatedness=20, cve=30, abandonment=15, blast_radius=15, compliance=15, license=5
        )
        assert w.outdatedness == 20

    def test_invalid_sum_raises(self) -> None:
        with pytest.raises(ValueError, match="sum to 100"):
            RiskWeights(outdatedness=10)  # sum = 10+30+15+15+10+5 = 85


# ---------------------------------------------------------------------------
# RiskThresholds
# ---------------------------------------------------------------------------


class TestRiskThresholds:
    def test_defaults(self) -> None:
        t = RiskThresholds()
        assert t.critical == 70
        assert t.high == 50
        assert t.medium == 30

    def test_invalid_order_raises(self) -> None:
        with pytest.raises(ValueError, match="medium <= high <= critical"):
            RiskThresholds(critical=40, high=50, medium=30)

    def test_level_for_critical(self) -> None:
        assert RiskThresholds().level_for(70) == RiskLevel.CRITICAL

    def test_level_for_high(self) -> None:
        assert RiskThresholds().level_for(50) == RiskLevel.HIGH

    def test_level_for_medium(self) -> None:
        assert RiskThresholds().level_for(30) == RiskLevel.MEDIUM

    def test_level_for_low(self) -> None:
        assert RiskThresholds().level_for(1) == RiskLevel.LOW

    def test_level_for_none(self) -> None:
        assert RiskThresholds().level_for(0) == RiskLevel.NONE

    def test_boundary_just_below_critical(self) -> None:
        assert RiskThresholds().level_for(69) == RiskLevel.HIGH


# ---------------------------------------------------------------------------
# DimensionScore
# ---------------------------------------------------------------------------


class TestDimensionScore:
    def test_construction(self) -> None:
        d = DimensionScore(
            name="CVE severity", score=20, cap=30, detail="2 advisories, worst: HIGH"
        )
        assert d.score == 20
        assert d.cap == 30


# ---------------------------------------------------------------------------
# LibraryRiskScore
# ---------------------------------------------------------------------------


def _dim(name: str, score: int, cap: int) -> DimensionScore:
    return DimensionScore(name=name, score=score, cap=cap, detail="test")


class TestLibraryRiskScore:
    def test_construction(self) -> None:
        lib = LibraryRiskScore(
            alias="retrofit",
            coordinate="com.squareup.retrofit2:retrofit",
            version="2.9.0",
            total_score=55,
            breakdown=(_dim("CVE severity", 20, 30), _dim("Outdatedness", 15, 25)),
            level=RiskLevel.HIGH,
        )
        assert lib.total_score == 55
        assert lib.level == RiskLevel.HIGH
        assert len(lib.breakdown) == 2

    def test_frozen(self) -> None:
        import dataclasses

        lib = LibraryRiskScore(
            alias="x",
            coordinate="a:b",
            version="1.0",
            total_score=0,
            breakdown=(),
            level=RiskLevel.NONE,
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            lib.alias = "changed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# RiskScoreReport
# ---------------------------------------------------------------------------


def _lib(alias: str, score: int, level: RiskLevel = RiskLevel.LOW) -> LibraryRiskScore:
    return LibraryRiskScore(
        alias=alias,
        coordinate=f"com.example:{alias}",
        version="1.0.0",
        total_score=score,
        breakdown=(_dim("CVE severity", score, 30),),
        level=level,
    )


class TestRiskScoreReport:
    def test_empty(self) -> None:
        rsr = RiskScoreReport(scored_libraries=(), libraries_scored=10)
        assert rsr.max_score == 0
        assert rsr.avg_score == 0.0
        assert rsr.critical_count == 0
        assert rsr.top == ()

    def test_top_capped_at_10(self) -> None:
        libs = tuple(_lib(f"lib{i}", 10 - i) for i in range(15))
        rsr = RiskScoreReport(scored_libraries=libs, libraries_scored=15)
        assert len(rsr.top) == 10

    def test_avg_score(self) -> None:
        libs = (_lib("a", 40), _lib("b", 60))
        rsr = RiskScoreReport(scored_libraries=libs, libraries_scored=2)
        assert rsr.avg_score == 50.0

    def test_avg_includes_zero_scorers(self) -> None:
        """avg_score divides by libraries_scored, which includes zero-scorers."""
        libs = (_lib("a", 60),)
        rsr = RiskScoreReport(scored_libraries=libs, libraries_scored=4)
        assert rsr.avg_score == 15.0  # 60 / 4

    def test_max_score(self) -> None:
        libs = (_lib("a", 80), _lib("b", 50))
        rsr = RiskScoreReport(scored_libraries=libs, libraries_scored=2)
        assert rsr.max_score == 80

    def test_critical_and_high_counts(self) -> None:
        libs = (
            _lib("a", 75, RiskLevel.CRITICAL),
            _lib("b", 72, RiskLevel.CRITICAL),
            _lib("c", 55, RiskLevel.HIGH),
        )
        rsr = RiskScoreReport(scored_libraries=libs, libraries_scored=3)
        assert rsr.critical_count == 2
        assert rsr.high_count == 1
