"""Risk score domain model (RFC-0008).

A 0-100 composite score per library, derived from six independent
dimensions. The score is always-opt-in at the CLI level (see ADR-0004)
but purely computational — no I/O required.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class RiskLevel(StrEnum):
    """Coarse risk band derived from the total score."""

    CRITICAL = "critical"  # >= critical threshold (default 70)
    HIGH = "high"  # >= high threshold (default 50)
    MEDIUM = "medium"  # >= medium threshold (default 30)
    LOW = "low"  # > 0
    NONE = "none"  # 0


@dataclass(frozen=True)
class RiskWeights:
    """Maximum contribution (cap) for each scoring dimension.

    The sum of all caps equals 100 so that a fully-compromised library
    scores exactly 100.  Individual dimension scores are clamped to their
    cap before summing.
    """

    outdatedness: int = 25
    cve: int = 30
    abandonment: int = 15
    blast_radius: int = 15
    compliance: int = 10
    license: int = 5

    def __post_init__(self) -> None:
        total = (
            self.outdatedness
            + self.cve
            + self.abandonment
            + self.blast_radius
            + self.compliance
            + self.license
        )
        if total != 100:
            raise ValueError(f"RiskWeights must sum to 100, got {total}")


@dataclass(frozen=True)
class RiskThresholds:
    """Score cutoffs that map a total score to a :class:`RiskLevel`."""

    critical: int = 70
    high: int = 50
    medium: int = 30

    def __post_init__(self) -> None:
        if not (self.medium <= self.high <= self.critical):
            raise ValueError("Thresholds must satisfy medium <= high <= critical")

    def level_for(self, score: int) -> RiskLevel:
        if score >= self.critical:
            return RiskLevel.CRITICAL
        if score >= self.high:
            return RiskLevel.HIGH
        if score >= self.medium:
            return RiskLevel.MEDIUM
        if score > 0:
            return RiskLevel.LOW
        return RiskLevel.NONE


@dataclass(frozen=True)
class DimensionScore:
    """Contribution of a single dimension to a library's risk score.

    Attributes:
        name:   Human-readable dimension label (e.g. ``"CVE severity"``).
        score:  Computed contribution (0 - cap).
        cap:    Maximum possible for this dimension (from :class:`RiskWeights`).
        detail: One-line explanation shown in the report breakdown.
    """

    name: str
    score: int
    cap: int
    detail: str


@dataclass(frozen=True)
class LibraryRiskScore:
    """Composite risk score for a single catalog library.

    Attributes:
        alias:       Catalog alias.
        coordinate:  ``"group:artifact"`` Maven coordinate.
        version:     Pinned version string.
        total_score: Sum of all dimension scores (0 - 100).
        breakdown:   Per-dimension contributions, ordered as in
                     :class:`RiskWeights`.
        level:       Coarse risk band derived from *total_score* and the
                     thresholds used during scoring.
    """

    alias: str
    coordinate: str
    version: str
    total_score: int
    breakdown: tuple[DimensionScore, ...]
    level: RiskLevel


@dataclass(frozen=True)
class RiskScoreReport:
    """Aggregate risk score results for an entire catalog.

    Only libraries with ``total_score > 0`` are included in
    *scored_libraries*; they are sorted descending by score so that
    the highest-risk entry is always first.

    Attributes:
        scored_libraries: Libraries with at least one non-zero dimension,
                          sorted by ``total_score`` descending.
        weights:          Dimension caps used for this run.
        thresholds:       Score band cutoffs used for this run.
        libraries_scored: Total number of catalog libraries that were
                          evaluated (including those that scored 0).
    """

    scored_libraries: tuple[LibraryRiskScore, ...]
    weights: RiskWeights = field(default_factory=RiskWeights)
    thresholds: RiskThresholds = field(default_factory=RiskThresholds)
    libraries_scored: int = 0

    @property
    def top(self) -> tuple[LibraryRiskScore, ...]:
        """Top-10 highest-risk libraries (fewer if catalog is smaller)."""
        return self.scored_libraries[:10]

    @property
    def avg_score(self) -> float:
        """Mean score across *all* scored libraries (including zero-scorers)."""
        if self.libraries_scored == 0:
            return 0.0
        total = sum(lib.total_score for lib in self.scored_libraries)
        return total / self.libraries_scored

    @property
    def max_score(self) -> int:
        """Highest individual library score, or 0 if no library scored."""
        if not self.scored_libraries:
            return 0
        return self.scored_libraries[0].total_score

    @property
    def critical_count(self) -> int:
        return sum(1 for lib in self.scored_libraries if lib.level == RiskLevel.CRITICAL)

    @property
    def high_count(self) -> int:
        return sum(1 for lib in self.scored_libraries if lib.level == RiskLevel.HIGH)
