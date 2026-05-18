"""Findings CSV writer — one row per finding across all sections (RFC-0017).

Event-centric flat log: every warning, error, and informational
finding detected during a single ``check`` run becomes one row,
tagged with its originating ``section`` so consumers can filter or
pivot. Complements :mod:`...inventory_csv_writer` (library-centric
join) — together they form the "technical audit trail" for
spreadsheet / BI ingestion.

Sections enumerated:

- ``Catalog Health`` — :class:`~...domain.finding.Finding`
- ``Compliance`` — :class:`~...domain.compliance.ComplianceFinding`
- ``Toolchain`` — :class:`~...domain.toolchain.ToolchainFinding`
- ``Library Health`` — :class:`~...domain.library_health.LibraryHealthFinding`
- ``Security`` — one row per :class:`~...domain.advisory.Advisory`
  inside each :class:`~...domain.advisory.LibraryAdvisory`
- ``License`` — :class:`~...domain.license.LicenseFinding` (only
  non-permissive)
- ``Changelog`` — :class:`~...domain.changelog.ChangelogEntry` whose
  ``breaking_signal`` is ``LIKELY``

Rows sorted by ``(section, target, rule_id)`` for stable diff-able
output. UTF-8 without BOM; ``csv.QUOTE_MINIMAL``.
"""

from __future__ import annotations

import csv
from pathlib import Path

from gradle_deps_monitor.domain import FreezeReport
from gradle_deps_monitor.domain.severity import CommonSeverity
from gradle_deps_monitor.infrastructure.writers._atomic import atomic_write

_COLUMNS: tuple[str, ...] = (
    "section",
    "rule_id",
    "severity",
    "common_severity",
    "target",
    "message",
    "recommendation",
)

# Synthetic rule IDs for sections whose finding types lack a stable
# rule_id field. The ID is part of the file's contract — consumers
# may filter / aggregate on it.
_LIBRARY_HEALTH_RULE_PREFIX = "library-health."
_LICENSE_RULE_PREFIX = "license."
_CHANGELOG_BREAKING_RULE = "changelog.breaking"


class FindingsCsvWriter:
    """Serialises every finding-shaped object on a
    :class:`~gradle_deps_monitor.domain.FreezeReport` to a flat CSV.
    RFC-0017 PR #2."""

    def write(self, report: FreezeReport, dest: Path) -> None:
        """Write *report* to *dest*, creating parent directories as needed."""
        rows = list(_iter_rows(report))
        rows.sort(key=lambda r: (r[0], r[4], r[1]))  # section, target, rule_id

        with atomic_write(dest, newline="") as fh:
            writer = csv.writer(fh, quoting=csv.QUOTE_MINIMAL)
            writer.writerow(_COLUMNS)
            writer.writerows(rows)


# ---------------------------------------------------------------------------
# Per-section row generators
# ---------------------------------------------------------------------------


def _iter_rows(report: FreezeReport):  # type: ignore[no-untyped-def]
    yield from _catalog_health_rows(report)
    yield from _compliance_rows(report)
    yield from _toolchain_rows(report)
    yield from _library_health_rows(report)
    yield from _security_rows(report)
    yield from _license_rows(report)
    yield from _changelog_rows(report)


def _catalog_health_rows(report: FreezeReport):  # type: ignore[no-untyped-def]
    for f in report.health_findings:
        yield (
            "Catalog Health",
            f.rule_id,
            f.severity.value,
            f.severity.to_common().value,
            "catalog",
            f.message,
            f.details or "",
        )


def _compliance_rows(report: FreezeReport):  # type: ignore[no-untyped-def]
    for f in report.compliance_findings:
        yield (
            "Compliance",
            f.rule_id,
            f.severity.value,
            f.severity.to_common().value,
            f.alias or "catalog",
            f.message,
            f.detail or "",
        )


def _toolchain_rows(report: FreezeReport):  # type: ignore[no-untyped-def]
    for f in report.toolchain_findings:
        yield (
            "Toolchain",
            f.rule_id,
            f.severity.value,
            f.severity.to_common().value,
            "catalog",
            f.message,
            f.recommendation,
        )


def _library_health_rows(report: FreezeReport):  # type: ignore[no-untyped-def]
    for f in report.library_health_findings:
        rec_parts = []
        if f.replacement:
            rec_parts.append(f"replacement: {f.replacement}")
        if f.migration_url:
            rec_parts.append(f"migration: {f.migration_url}")
        yield (
            "Library Health",
            f"{_LIBRARY_HEALTH_RULE_PREFIX}{f.signal.value}",
            f.severity.value,
            f.severity.to_common().value,
            f.alias,
            f.message,
            "; ".join(rec_parts),
        )


def _security_rows(report: FreezeReport):  # type: ignore[no-untyped-def]
    for la in report.security_advisories:
        for adv in la.advisories:
            rec = f"fixed in {adv.fixed_version}" if adv.fixed_version else ""
            yield (
                "Security",
                adv.ghsa_id,
                adv.severity.value,
                adv.severity.to_common().value,
                la.alias,
                adv.summary,
                rec,
            )


def _license_rows(report: FreezeReport):  # type: ignore[no-untyped-def]
    audit = report.license_audit
    if audit is None:
        return
    for f in audit.findings:
        # License findings carry no severity field of their own; map
        # the tier into the common vocabulary so the row remains
        # comparable to the others. Strong copyleft is the only tier
        # an integrator typically must act on; the others are advisory.
        common = (
            CommonSeverity.ERROR if f.tier.value == "strong_copyleft" else CommonSeverity.WARNING
        )
        yield (
            "License",
            f"{_LICENSE_RULE_PREFIX}{f.tier.value}",
            f.tier.value,
            common.value,
            f.alias,
            f"{f.license_name or '(not declared)'} — {f.coordinate}",
            "",
        )


def _changelog_rows(report: FreezeReport):  # type: ignore[no-untyped-def]
    for e in report.changelog_entries:
        # Only LIKELY-breaking upgrades are surfaced as findings —
        # CLEAN / UNKNOWN are informational and live in the
        # major_upgrades.changelog_stats counters on the report.
        if e.breaking_signal.value != "likely":
            continue
        rec = f"see {e.changelog_url}" if e.changelog_url else ""
        yield (
            "Changelog",
            _CHANGELOG_BREAKING_RULE,
            "likely-breaking",
            CommonSeverity.WARNING.value,
            e.alias,
            f"{e.coordinate}: {e.pinned_version} → {e.latest_version}",
            rec,
        )
