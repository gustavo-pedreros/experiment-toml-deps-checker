"""compute_risk_score — application service for RFC-0008.

Pure computation: takes the already-built domain objects (changelog
entries, advisories, health findings, usage map, license audit) and
produces a :class:`~gradle_deps_monitor.domain.risk_score.RiskScoreReport`.

No I/O. No external dependencies. Safe to call synchronously inside
:meth:`~gradle_deps_monitor.application.generate_freeze_report.GenerateFreezeReport.execute`.
"""

from __future__ import annotations

from gradle_deps_monitor.domain.advisory import AdvisorySeverity, LibraryAdvisory
from gradle_deps_monitor.domain.bom import VersionSource
from gradle_deps_monitor.domain.catalog import Library
from gradle_deps_monitor.domain.changelog import ChangelogEntry
from gradle_deps_monitor.domain.library_health import LibraryHealthFinding, LibraryHealthSeverity
from gradle_deps_monitor.domain.license import LicenseAudit, LicenseTier
from gradle_deps_monitor.domain.module_usage import ModuleUsageMap
from gradle_deps_monitor.domain.risk_score import (
    DimensionScore,
    LibraryRiskScore,
    RiskScoreReport,
    RiskThresholds,
    RiskWeights,
)
from gradle_deps_monitor.domain.version_status import (
    LibraryVersionStatus,
    VersionDrift,
    major_delta,
)


def score_libraries(
    libraries: tuple[Library, ...],
    changelog_entries: tuple[ChangelogEntry, ...],
    security_advisories: tuple[LibraryAdvisory, ...],
    library_health_findings: tuple[LibraryHealthFinding, ...],
    module_usage_map: ModuleUsageMap | None,
    license_audit: LicenseAudit | None,
    version_statuses: tuple[LibraryVersionStatus, ...] = (),
    weights: RiskWeights | None = None,
    thresholds: RiskThresholds | None = None,
) -> RiskScoreReport:
    """Compute a :class:`RiskScoreReport` from pre-built report data.

    :param libraries:             All catalog libraries to score.
    :param changelog_entries:     Major upgrade entries from the changelog fetcher.
                                  Used as a fallback for outdatedness when no
                                  version-status resolver is wired in.
    :param security_advisories:   CVE advisories from the vulnerability scanner.
    :param library_health_findings: Deprecation/inactivity findings.
    :param module_usage_map:      Optional module usage scan result.
    :param license_audit:         Optional license audit result.
    :param version_statuses:      Per-library latest-vs-pinned drift from
                                  RFC-0013. When non-empty, drives the
                                  outdatedness dimension; otherwise the
                                  scorer falls back to *changelog_entries*
                                  (major-only) for backwards compatibility.
    :param weights:               Custom dimension caps. ``None`` uses defaults.
    :param thresholds:            Custom score band cutoffs. ``None`` uses defaults.
    :returns:                     A :class:`RiskScoreReport` sorted by total score
                                  descending.
    """
    w = weights or RiskWeights()
    t = thresholds or RiskThresholds()

    # Build fast-lookup indexes -------------------------------------------------
    changelog_by_alias: dict[str, ChangelogEntry] = {e.alias: e for e in changelog_entries}
    advisories_by_alias: dict[str, LibraryAdvisory] = {
        la.alias: la for la in security_advisories if la.is_vulnerable
    }
    health_by_alias: dict[str, LibraryHealthFinding] = {f.alias: f for f in library_health_findings}
    license_finding_by_alias = {}
    if license_audit is not None:
        for lf in license_audit.findings:
            license_finding_by_alias[lf.alias] = lf
    version_status_by_alias: dict[str, LibraryVersionStatus] = {
        s.alias: s for s in version_statuses
    }

    # Score each library -------------------------------------------------------
    scored: list[LibraryRiskScore] = []
    for lib in libraries:
        # RFC-0014: a library managed by a BoM inherits the BoM's
        # outdatedness signal — bumping the BoM is what drives the upgrade.
        outdatedness_alias = lib.alias
        if lib.version_source == VersionSource.FROM_BOM and lib.bom_alias:
            outdatedness_alias = lib.bom_alias

        breakdown = (
            _score_outdatedness(
                outdatedness_alias, version_status_by_alias, changelog_by_alias, w.outdatedness
            ),
            _score_cve(lib.alias, advisories_by_alias, w.cve),
            _score_abandonment(lib.alias, health_by_alias, w.abandonment),
            _score_blast_radius(lib.alias, module_usage_map, w.blast_radius),
            _score_compliance(w.compliance),
            _score_license(lib.alias, license_finding_by_alias, license_audit, w.license),
        )
        total = sum(d.score for d in breakdown)
        if total > 0:
            scored.append(
                LibraryRiskScore(
                    alias=lib.alias,
                    coordinate=f"{lib.group}:{lib.artifact}",
                    version=lib.version.raw,
                    total_score=total,
                    breakdown=breakdown,
                    level=t.level_for(total),
                )
            )

    scored.sort(key=lambda x: -x.total_score)
    return RiskScoreReport(
        scored_libraries=tuple(scored),
        weights=w,
        thresholds=t,
        libraries_scored=len(libraries),
    )


# ---------------------------------------------------------------------------
# Per-dimension scoring helpers
# ---------------------------------------------------------------------------


def _parse_major(version: str) -> int:
    """Extract the major component of a dotted version string."""
    try:
        return int(version.split(".")[0])
    except (ValueError, IndexError):
        return 0


def _score_outdatedness(
    alias: str,
    version_status_by_alias: dict[str, LibraryVersionStatus],
    changelog_by_alias: dict[str, ChangelogEntry],
    cap: int,
) -> DimensionScore:
    """Score based on the gap to the latest stable release.

    Per RFC-0008 spec, with RFC-0013 wiring:

    .. code-block:: text

        NONE  / UNKNOWN drift   →  0
        PATCH                   →  min( 5, cap)
        MINOR                   →  min(10, cap)
        MAJOR (1 behind)        →  min(20, cap)
        MAJOR (≥2 behind)       →  cap

    When a :class:`LibraryVersionStatus` is available it drives the
    score. Otherwise, the function falls back to the major-only
    *changelog_by_alias* signal so older callers keep working.
    """
    status = version_status_by_alias.get(alias)
    if status is not None:
        return _score_from_version_status(status, cap)
    return _score_from_changelog(alias, changelog_by_alias, cap)


def _score_from_version_status(status: LibraryVersionStatus, cap: int) -> DimensionScore:
    pinned_str = status.pinned.raw
    latest_str = status.latest.raw if status.latest is not None else "?"
    drift = status.drift

    if drift in (VersionDrift.NONE, VersionDrift.UNKNOWN):
        return DimensionScore("Outdatedness", 0, cap, "up to date")
    if drift == VersionDrift.PATCH:
        return DimensionScore(
            "Outdatedness", min(5, cap), cap, f"1 patch behind ({pinned_str} → {latest_str})"
        )
    if drift == VersionDrift.MINOR:
        return DimensionScore(
            "Outdatedness", min(10, cap), cap, f"1 minor behind ({pinned_str} → {latest_str})"
        )
    # MAJOR — distinguish 1 from ≥2 majors behind for the spec's full curve
    diff = major_delta(status.pinned, status.latest)
    if diff <= 1:
        return DimensionScore(
            "Outdatedness", min(20, cap), cap, f"1 major behind ({pinned_str} → {latest_str})"
        )
    return DimensionScore(
        "Outdatedness", cap, cap, f"{diff} majors behind ({pinned_str} → {latest_str})"
    )


def _score_from_changelog(
    alias: str,
    changelog_by_alias: dict[str, ChangelogEntry],
    cap: int,
) -> DimensionScore:
    """Major-only fallback used when no :class:`LibraryVersionStatus` is available."""
    entry = changelog_by_alias.get(alias)
    if entry is None:
        return DimensionScore("Outdatedness", 0, cap, "up to date")

    pinned_major = _parse_major(entry.pinned_version)
    latest_major = _parse_major(entry.latest_version)
    diff = max(0, latest_major - pinned_major)

    if diff == 0:
        return DimensionScore("Outdatedness", 0, cap, "up to date")
    if diff == 1:
        score = min(20, cap)
        detail = f"1 major behind ({entry.pinned_version} → {entry.latest_version})"
    else:
        score = cap
        detail = f"{diff} majors behind ({entry.pinned_version} → {entry.latest_version})"
    return DimensionScore("Outdatedness", score, cap, detail)


def _score_cve(
    alias: str,
    advisories_by_alias: dict[str, LibraryAdvisory],
    cap: int,
) -> DimensionScore:
    """Score based on known CVE advisories.

    Per-advisory points: CRITICAL=30, HIGH=20, MEDIUM=10, LOW=5.
    The raw sum is clamped to *cap*.
    """
    la = advisories_by_alias.get(alias)
    if la is None:
        return DimensionScore("CVE severity", 0, cap, "no advisories")

    _points: dict[AdvisorySeverity, int] = {
        AdvisorySeverity.CRITICAL: 30,
        AdvisorySeverity.HIGH: 20,
        AdvisorySeverity.MEDIUM: 10,
        AdvisorySeverity.LOW: 5,
        AdvisorySeverity.UNKNOWN: 5,
    }
    raw = sum(_points.get(adv.severity, 5) for adv in la.advisories)
    score = min(raw, cap)
    count = len(la.advisories)
    worst = la.max_severity
    worst_label = worst.upper() if worst else "UNKNOWN"
    detail = f"{count} {'advisory' if count == 1 else 'advisories'}, worst: {worst_label}"
    return DimensionScore("CVE severity", score, cap, detail)


def _score_abandonment(
    alias: str,
    health_by_alias: dict[str, LibraryHealthFinding],
    cap: int,
) -> DimensionScore:
    """Score based on library deprecation / inactivity findings."""
    finding = health_by_alias.get(alias)
    if finding is None:
        return DimensionScore("Abandonment", 0, cap, "active")

    if finding.severity == LibraryHealthSeverity.HIGH:
        # Officially deprecated or relocated → full cap
        return DimensionScore("Abandonment", cap, cap, finding.message)

    if finding.severity == LibraryHealthSeverity.MEDIUM:
        # Inactive — scale by age
        days = finding.days_since_release or 730
        if days >= 1460:  # 4+ years
            score = cap
        elif days >= 1095:  # 3+ years
            score = min(cap, 11)
        else:  # 2+ years (minimum to trigger MEDIUM)
            score = min(cap, 7)
        months = days // 30
        detail = f"inactive ~{months} months"
        return DimensionScore("Abandonment", score, cap, detail)

    # LOW
    return DimensionScore("Abandonment", min(cap, 3), cap, finding.message)


def _score_blast_radius(
    alias: str,
    usage_map: ModuleUsageMap | None,
    cap: int,
) -> DimensionScore:
    """Score based on number of Gradle modules directly using this library."""
    if usage_map is None:
        return DimensionScore("Blast radius", 0, cap, "not scanned")

    usage = next((u for u in usage_map.library_usages if u.alias == alias), None)
    if usage is None or usage.direct_count == 0:
        return DimensionScore("Blast radius", 0, cap, "not used")

    count = usage.direct_count
    if count <= 5:
        score = 3
    elif count <= 15:
        score = 7
    elif count <= 30:
        score = 11
    else:
        score = cap

    module_word = "module" if count == 1 else "modules"
    return DimensionScore("Blast radius", min(score, cap), cap, f"{count} {module_word}")


def _score_compliance(cap: int) -> DimensionScore:
    """Compliance dimension — always 0 for now.

    ComplianceFinding has no ``alias`` field so findings cannot be
    attributed to individual libraries.  The dimension is reserved for
    a future RFC that adds per-library compliance rules.
    """
    return DimensionScore("Compliance", 0, cap, "catalog-level (not library-specific)")


def _score_license(
    alias: str,
    license_finding_by_alias: dict,  # type: ignore[type-arg]
    license_audit: LicenseAudit | None,
    cap: int,
) -> DimensionScore:
    """Score based on license tier from the RFC-0009 audit."""
    if license_audit is None:
        return DimensionScore("License", 0, cap, "audit not run")

    finding = license_finding_by_alias.get(alias)
    if finding is None:
        # Not in findings → permissive (only non-permissive are stored)
        return DimensionScore("License", 0, cap, "permissive")

    tier = finding.tier
    name = finding.license_name or "unknown license"
    if tier == LicenseTier.STRONG_COPYLEFT:
        return DimensionScore("License", cap, cap, f"{name} (strong copyleft)")
    if tier == LicenseTier.WEAK_COPYLEFT:
        score = max(1, cap // 2)
        return DimensionScore("License", score, cap, f"{name} (weak copyleft)")
    # UNKNOWN
    score = max(1, (cap * 3) // 5)
    return DimensionScore("License", score, cap, "license unknown")
