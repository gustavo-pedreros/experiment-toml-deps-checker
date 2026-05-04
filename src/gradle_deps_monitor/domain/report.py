"""FreezeReport — the aggregate root of the domain (ADR-0007)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from gradle_deps_monitor.domain.catalog import Catalog


@dataclass(frozen=True)
class FreezeReport:
    """Snapshot of a Gradle catalog produced at a single point in time.

    This is the aggregate root. The ``GenerateFreezeReport`` use case
    (Phase 1, Step 4) is the only factory that constructs instances.

    Attributes added in later steps:
    - ``check_results`` — output of each :mod:`~gradle_deps_monitor.checks` rule
    - ``git_ref`` — the tag or commit SHA this report is anchored to
    """

    catalog: Catalog
    generated_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))

    def __post_init__(self) -> None:
        if self.generated_at.tzinfo is None:
            raise ValueError("generated_at must be timezone-aware")
