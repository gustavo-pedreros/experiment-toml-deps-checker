"""Application configuration aggregate (RFC-0012).

Captures every per-project tunable in a single immutable DTO. Loading the
file from disk and validating its content is the responsibility of the
infrastructure layer
(:mod:`gradle_deps_monitor.infrastructure.config.loader`); this module
only declares the shape and the defaults so the domain can stay free of
I/O.

Resolution order
----------------
For every setting:

1. Built-in defaults (this module)
2. ``gradle-deps-monitor.toml`` at the project root
3. Environment variables (where applicable)
4. CLI flags

Higher steps override lower ones.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from gradle_deps_monitor.domain.risk_score import RiskThresholds, RiskWeights


@dataclass(frozen=True)
class AppConfig:
    """Top-level application configuration.

    All sections are optional: an empty config produces the defaults
    documented in each nested DTO. The dataclass is frozen so that
    downstream code cannot mutate config values picked up from disk —
    overrides must go back through the loader.

    :param risk_weights:    Caps for each risk-score dimension. Sum must
                            equal 100; validated by
                            :class:`~gradle_deps_monitor.domain.risk_score.RiskWeights`.
    :param risk_thresholds: Score cutoffs that map a numeric score to a
                            :class:`~gradle_deps_monitor.domain.risk_score.RiskLevel`.
    """

    risk_weights: RiskWeights = field(default_factory=RiskWeights)
    risk_thresholds: RiskThresholds = field(default_factory=RiskThresholds)
