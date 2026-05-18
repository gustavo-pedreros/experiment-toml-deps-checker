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
from pathlib import Path

from gradle_deps_monitor.domain.risk_score import RiskThresholds, RiskWeights


@dataclass(frozen=True)
class CacheConfig:
    """Persistent-cache tunables (RFC-0029).

    ``root`` is the on-disk directory the diskcache layers write into;
    when ``None``, the application resolves a default at runtime
    (``GRADLE_DEPS_MONITOR_CACHE_ROOT`` env var, then
    ``~/.cache/gradle-deps-monitor``).

    ``ttl_seconds_maven`` applies to Maven Central + Google Maven
    metadata; ``ttl_seconds_advisory`` applies to GitHub Advisory DB
    and OSS Index responses. Bypass / purge / per-run TTL override are
    not exposed here — those are per-invocation CLI flags handled in
    :mod:`gradle_deps_monitor.bootstrap`.
    """

    root: Path | None = None
    ttl_seconds_maven: int = 3600
    ttl_seconds_advisory: int = 86_400


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
    :param cache:           Persistent-cache configuration. See
                            :class:`CacheConfig`.
    """

    risk_weights: RiskWeights = field(default_factory=RiskWeights)
    risk_thresholds: RiskThresholds = field(default_factory=RiskThresholds)
    cache: CacheConfig = field(default_factory=CacheConfig)
