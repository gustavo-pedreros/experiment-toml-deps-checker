"""Unit tests for the AppConfig domain DTO (RFC-0012)."""

from __future__ import annotations

import dataclasses

import pytest

from gradle_deps_monitor.domain.config import AppConfig
from gradle_deps_monitor.domain.risk_score import RiskThresholds, RiskWeights


class TestAppConfigDefaults:
    def test_defaults_use_risk_score_defaults(self) -> None:
        cfg = AppConfig()
        assert cfg.risk_weights == RiskWeights()
        assert cfg.risk_thresholds == RiskThresholds()

    def test_default_weights_sum_to_100(self) -> None:
        cfg = AppConfig()
        w = cfg.risk_weights
        assert (
            w.outdatedness + w.cve + w.abandonment + w.blast_radius + w.compliance + w.license
            == 100
        )


class TestAppConfigCustom:
    def test_custom_weights(self) -> None:
        custom_weights = RiskWeights(
            outdatedness=20,
            cve=40,
            abandonment=15,
            blast_radius=10,
            compliance=10,
            license=5,
        )
        cfg = AppConfig(risk_weights=custom_weights)
        assert cfg.risk_weights.cve == 40
        assert cfg.risk_thresholds == RiskThresholds()  # default

    def test_custom_thresholds(self) -> None:
        cfg = AppConfig(risk_thresholds=RiskThresholds(critical=80, high=60, medium=40))
        assert cfg.risk_thresholds.critical == 80


class TestAppConfigImmutability:
    def test_frozen(self) -> None:
        cfg = AppConfig()
        with pytest.raises(dataclasses.FrozenInstanceError):
            cfg.risk_weights = RiskWeights()  # type: ignore[misc]
