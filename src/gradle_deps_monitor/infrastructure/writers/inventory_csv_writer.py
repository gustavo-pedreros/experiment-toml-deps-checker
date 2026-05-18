"""Inventory CSV writer — one row per catalog library (RFC-0017).

Library-centric flat join: every library in the catalog becomes one
row with every dimension (version, drift, CVE count, license tier,
BoM parent, duplicates, etc.) collapsed into a single record. This
is the cross-section view that issue #13 from the 2026-05 stress-
test menu was asking for — readers see the compound story
("the duplicate is the reason you're exposed to the older CVE") by
filtering / pivoting in Excel rather than manually correlating
findings across Markdown sections.

**Empty-cell semantics:** an empty cell means "this dimension didn't
run / not applicable" (e.g. ``risk_score`` is empty when
``--risk-score`` is off). Zero or a value means "ran, this is the
result". A separate follow-up RFC will add explicit ``*_scanned``
flags to the JSON / Markdown reports for full parity.

Excel-compatible CSV via the stdlib ``csv`` module with
``QUOTE_MINIMAL``. UTF-8 without BOM (the BOM breaks Python
consumers; modern Excel and Sheets read UTF-8 cleanly).
"""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

from gradle_deps_monitor.domain import FreezeReport
from gradle_deps_monitor.domain.advisory import LibraryAdvisory
from gradle_deps_monitor.domain.catalog import Library
from gradle_deps_monitor.domain.library_health import LibraryHealthFinding
from gradle_deps_monitor.domain.module_usage import LibraryUsage
from gradle_deps_monitor.domain.risk_score import LibraryRiskScore
from gradle_deps_monitor.domain.version_status import LibraryVersionStatus

# Column order is part of the file's contract. Append new columns at
# the end in future revisions; never reorder or rename without a
# documented migration.
_COLUMNS: tuple[str, ...] = (
    "alias",
    "coordinate",
    "version",
    "stability_tier",
    "latest_stable",
    "drift",
    "risk_score",
    "risk_level",
    "usage_count",
    "vulnerability_count",
    "compliance_issues",
    "license_tier",
    "health_status",
    "bom_parent",
    "duplicate_of",
)


class InventoryCsvWriter:
    """Serialises a :class:`~gradle_deps_monitor.domain.FreezeReport` to
    a library-centric CSV. RFC-0017."""

    def write(self, report: FreezeReport, dest: Path) -> None:
        """Write *report* to *dest*, creating parent directories as needed."""
        dest.parent.mkdir(parents=True, exist_ok=True)

        index = _Indexes(report)

        with dest.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.writer(fh, quoting=csv.QUOTE_MINIMAL)
            writer.writerow(_COLUMNS)
            for lib in sorted(report.catalog.libraries, key=lambda lib: lib.alias):
                writer.writerow(_row(lib, index))


# ---------------------------------------------------------------------------
# Per-row indexes — built once per report to keep per-library lookup O(1)
# ---------------------------------------------------------------------------


class _Indexes:
    """Caches per-alias lookups across the FreezeReport sections."""

    def __init__(self, report: FreezeReport) -> None:
        self.report = report

        # status by alias (None when no resolver injected → empty cells)
        self.status_by_alias = {s.alias: s for s in report.library_version_statuses}

        # risk score by alias (only libs with total_score > 0 are in
        # scored_libraries; libs not present scored 0 / RiskLevel.NONE)
        rsr = report.risk_score_report
        self.risk_by_alias = {r.alias: r for r in rsr.scored_libraries} if rsr is not None else {}
        self.risk_score_enabled = rsr is not None

        # usage by alias (None when --module-usage off → empty cells)
        usage = report.module_usage_map
        self.usage_by_alias = (
            {u.alias: u for u in usage.library_usages} if usage is not None else {}
        )
        self.usage_enabled = usage is not None

        # vulnerability count by alias. security_advisories is one
        # LibraryAdvisory per library when the scanner ran (with possibly
        # zero advisories each). Empty tuple → scanner didn't run.
        self.advisory_by_alias = {la.alias: la for la in report.security_advisories}
        self.security_scanned = len(report.security_advisories) > 0

        # compliance issues grouped by alias. Catalog-level findings
        # (alias is None) are excluded from per-library cells; they
        # show up in findings.csv with target="catalog".
        self.compliance_by_alias: dict[str, list[str]] = defaultdict(list)
        for cf in report.compliance_findings:
            if cf.alias:
                self.compliance_by_alias[cf.alias].append(cf.rule_id)

        # License tier by alias. audit.findings holds only non-permissive
        # entries; libs scanned-and-permissive must be derived from
        # absence + the fact that scan ran (audit is not None).
        self.license_audit = report.license_audit
        self.flagged_license_by_alias = (
            {lf.alias: lf for lf in self.license_audit.findings}
            if self.license_audit is not None
            else {}
        )

        # Library health signal by alias. A lib with no finding from a
        # scanner that ran → "active". Scanner not having run is
        # indistinguishable today from "no findings" without a
        # *_scanned flag (covered by the follow-up #5 RFC); use the
        # convention "any finding exists → scanner ran".
        self.library_health_by_alias = {f.alias: f for f in report.library_health_findings}
        self.library_health_scanned = len(report.library_health_findings) > 0

        # Duplicate detection: group catalog libs by (group, artifact)
        # and pre-compute the cross-link for each alias. The aliases
        # share the same coordinate; cross-section #13 emerges naturally
        # when the reader filters by vulnerability_count > 0 in Excel.
        coord_to_aliases: dict[tuple[str, str], list[str]] = defaultdict(list)
        for lib in report.catalog.libraries:
            coord_to_aliases[(lib.group, lib.artifact)].append(lib.alias)
        self.duplicates_by_alias: dict[str, list[str]] = {}
        for aliases in coord_to_aliases.values():
            if len(aliases) < 2:
                continue
            for alias in aliases:
                self.duplicates_by_alias[alias] = sorted(a for a in aliases if a != alias)


# ---------------------------------------------------------------------------
# Row construction
# ---------------------------------------------------------------------------


def _row(lib: Library, idx: _Indexes) -> tuple[str, ...]:
    """Compose one CSV row for *lib*. Empty cells follow the
    semantics documented in the module docstring."""
    status = idx.status_by_alias.get(lib.alias)
    risk = idx.risk_by_alias.get(lib.alias)
    usage = idx.usage_by_alias.get(lib.alias)
    advisory = idx.advisory_by_alias.get(lib.alias)
    compliance_ids = idx.compliance_by_alias.get(lib.alias, [])
    health = idx.library_health_by_alias.get(lib.alias)
    duplicates = idx.duplicates_by_alias.get(lib.alias, [])

    return (
        lib.alias,
        lib.coordinate,
        str(lib.version),
        lib.version.stability.value,
        _latest_stable(status),
        _drift(status),
        _risk_score(risk, idx.risk_score_enabled),
        _risk_level(risk, idx.risk_score_enabled),
        _usage_count(usage, idx.usage_enabled),
        _vulnerability_count(advisory, idx.security_scanned),
        ",".join(compliance_ids),
        _license_tier(lib.alias, idx),
        _health_status(health, idx.library_health_scanned),
        lib.bom_alias or "",
        ",".join(duplicates),
    )


def _latest_stable(status: LibraryVersionStatus | None) -> str:
    if status is None or status.latest is None:
        return ""
    return status.latest.raw


def _drift(status: LibraryVersionStatus | None) -> str:
    if status is None:
        return ""
    return str(status.drift.value)


def _risk_score(risk: LibraryRiskScore | None, enabled: bool) -> str:
    if not enabled:
        return ""
    return str(risk.total_score) if risk is not None else "0"


def _risk_level(risk: LibraryRiskScore | None, enabled: bool) -> str:
    if not enabled:
        return ""
    if risk is None:
        # libs not in scored_libraries had total_score 0 and so were filtered;
        # their effective level is the lowest band — express as "none".
        return "none"
    return str(risk.level.value)


def _usage_count(usage: LibraryUsage | None, enabled: bool) -> str:
    if not enabled:
        return ""
    return str(usage.direct_count) if usage is not None else "0"


def _vulnerability_count(advisory: LibraryAdvisory | None, scanned: bool) -> str:
    if not scanned:
        return ""
    return str(len(advisory.advisories)) if advisory is not None else "0"


def _license_tier(alias: str, idx: _Indexes) -> str:
    if idx.license_audit is None:
        return ""
    flagged = idx.flagged_license_by_alias.get(alias)
    if flagged is not None:
        return str(flagged.tier.value)
    # Audit ran and this lib isn't in findings → permissive by
    # construction (only non-permissive are stored in audit.findings).
    return "permissive"


def _health_status(health: LibraryHealthFinding | None, scanned: bool) -> str:
    if not scanned:
        return ""
    if health is None:
        return "active"
    return str(health.signal.value)
