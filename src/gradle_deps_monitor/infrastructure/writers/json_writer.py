"""JSON report writer."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from gradle_deps_monitor.domain import FreezeReport
from gradle_deps_monitor.domain.advisory import Advisory, LibraryAdvisory
from gradle_deps_monitor.domain.bom import BomResolution
from gradle_deps_monitor.domain.catalog import Bundle, Library, Plugin
from gradle_deps_monitor.domain.changelog import ChangelogEntry
from gradle_deps_monitor.domain.compliance import ComplianceFinding
from gradle_deps_monitor.domain.finding import Finding
from gradle_deps_monitor.domain.library_health import LibraryHealthFinding
from gradle_deps_monitor.domain.license import LicenseAudit
from gradle_deps_monitor.domain.module_usage import ModuleUsageMap
from gradle_deps_monitor.domain.risk_score import RiskScoreReport
from gradle_deps_monitor.domain.toolchain import ToolchainFinding
from gradle_deps_monitor.domain.version_status import LibraryVersionStatus

# Schema version for the freeze.json output. Follows SemVer per ADR-0008:
#   - MAJOR (x.0.0): breaking changes (removed/renamed fields, type changes)
#   - MINOR (1.x.0): additive changes (new fields, new optional values)
#   - PATCH (1.0.x): wire-format-equivalent changes
# Consumers reading 1.x MUST tolerate unknown fields and unknown enum values.
SCHEMA_VERSION = "1.5.0"


class JsonWriter:
    """Serialises a :class:`~gradle_deps_monitor.domain.FreezeReport` to pretty-printed JSON."""

    def write(self, report: FreezeReport, dest: Path) -> None:
        """Write *report* to *dest*, creating parent directories as needed."""
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(
            json.dumps(_serialise(report), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------


def _serialise(report: FreezeReport) -> dict[str, Any]:
    cat = report.catalog
    libs = sorted(cat.libraries, key=lambda lib: lib.alias)
    plugins = sorted(cat.plugins, key=lambda p: p.alias)
    bundles = sorted(cat.bundles, key=lambda b: b.alias)
    status_by_alias = {s.alias: s for s in report.library_version_statuses}

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": report.generated_at.isoformat(timespec="seconds"),
        "catalog": {
            "source_path": str(cat.source_path),
            "library_count": cat.library_count,
            "plugin_count": cat.plugin_count,
            "bundle_count": len(cat.bundles),
            "libraries": [_lib(lib, status_by_alias.get(lib.alias)) for lib in libs],
            "plugins": [_plugin(p) for p in plugins],
            "bundles": [_bundle(b) for b in bundles],
        },
        "version_status": _version_status_summary(report),
        "boms": [_bom(b) for b in report.bom_resolutions],
        "health": {
            "finding_count": len(report.health_findings),
            "findings": [_finding(f) for f in report.health_findings],
        },
        "security": {
            "scanned": len(report.security_advisories) > 0,
            "vulnerable_count": len(report.vulnerable_libraries),
            "libraries": [_library_advisory(la) for la in report.vulnerable_libraries],
        },
        "compliance": {
            "finding_count": len(report.compliance_findings),
            "has_violations": report.has_compliance_violations,
            "findings": [_compliance_finding(f) for f in report.compliance_findings],
        },
        "toolchain": {
            "finding_count": len(report.toolchain_findings),
            "has_errors": report.has_toolchain_errors,
            "findings": [_toolchain_finding(f) for f in report.toolchain_findings],
        },
        "library_health": {
            "finding_count": len(report.library_health_findings),
            "has_deprecated": report.has_deprecated_libraries,
            "findings": [_library_health_finding(f) for f in report.library_health_findings],
        },
        "major_upgrades": {
            "upgrade_count": len(report.changelog_entries),
            "has_breaking": report.has_breaking_upgrades,
            "entries": [_changelog_entry(e) for e in report.changelog_entries],
        },
        "module_usage_map": _module_usage_map(report.module_usage_map),
        "license_audit": _license_audit(report.license_audit),
        "risk_score": _risk_score(report.risk_score_report),
    }


def _lib(lib: Library, status: LibraryVersionStatus | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "alias": lib.alias,
        "group": lib.group,
        "artifact": lib.artifact,
        "version": str(lib.version),
        "stability": lib.version.stability.value,
        "version_source": lib.version_source.value,
    }
    if lib.bom_alias is not None:
        payload["bom_alias"] = lib.bom_alias
    if lib.version_constraints is not None:
        rv = lib.version_constraints
        # Only emit keys actually declared in the catalog, to keep the
        # output minimal and unambiguous. Empty ``reject`` is omitted.
        constraints: dict[str, Any] = {}
        if rv.strictly is not None:
            constraints["strictly"] = rv.strictly
        if rv.require is not None:
            constraints["require"] = rv.require
        if rv.prefer is not None:
            constraints["prefer"] = rv.prefer
        if rv.reject:
            constraints["reject"] = list(rv.reject)
        payload["version_constraints"] = constraints
    if status is not None:
        payload["version_status"] = {
            "latest": status.latest.raw if status.latest is not None else None,
            "drift": status.drift.value,
        }
    return payload


def _bom(resolution: BomResolution) -> dict[str, Any]:
    return {
        "alias": resolution.bom_alias,
        "coordinate": resolution.bom_coordinate,
        "version": resolution.bom_version.raw,
        "managed_count": len(resolution.managed),
        "managed": [
            {
                "group": m.group,
                "artifact": m.artifact,
                "version": m.version.raw,
            }
            for m in resolution.managed
        ],
    }


def _version_status_summary(report: FreezeReport) -> dict[str, Any] | None:
    """Top-level summary of drift counts (RFC-0013).

    Returns ``None`` when no version-status data is present so consumers
    on ``schema_version`` 1.0.0 don't see a key with empty content.
    """
    if not report.library_version_statuses:
        return None
    return {
        "library_count": len(report.library_version_statuses),
        "outdated_count": len(report.outdated_libraries),
        "major_outdated": report.major_outdated_count,
        "minor_outdated": report.minor_outdated_count,
        "patch_outdated": report.patch_outdated_count,
    }


def _plugin(p: Plugin) -> dict[str, Any]:
    return {
        "alias": p.alias,
        "id": p.id,
        "version": str(p.version),
        "stability": p.version.stability.value,
    }


def _bundle(b: Bundle) -> dict[str, Any]:
    return {
        "alias": b.alias,
        "members": sorted(b.member_aliases),
    }


def _library_advisory(la: LibraryAdvisory) -> dict[str, Any]:
    return {
        "alias": la.alias,
        "coordinate": la.coordinate,
        "version": la.version,
        "advisories": [_advisory(a) for a in la.advisories],
    }


def _advisory(a: Advisory) -> dict[str, Any]:
    result: dict[str, Any] = {
        "ghsa_id": a.ghsa_id,
        "severity": a.severity.value,
        # RFC-0016b (schema 1.4.0+): cross-section severity for dashboards
        # that want to chart "errors across all sections" without knowing
        # each section's local vocabulary.
        "common_severity": a.severity.to_common().value,
        "summary": a.summary,
        "url": a.url,
        "source": a.source,
    }
    if a.cve_id:
        result["cve_id"] = a.cve_id
    if a.fixed_version:
        result["fixed_version"] = a.fixed_version
    return result


def _compliance_finding(f: ComplianceFinding) -> dict[str, Any]:
    result: dict[str, Any] = {
        "rule_id": f.rule_id,
        "severity": f.severity.value,
        "common_severity": f.severity.to_common().value,
        "message": f.message,
    }
    if f.detail:
        result["detail"] = f.detail
    if f.deadline:
        result["deadline"] = f.deadline
    if f.migration:
        result["migration"] = f.migration
    # RFC-0015 (schema 1.3.0+): optional library attribution. Omitted for
    # catalog-level findings so consumers on schema 1.2.x don't see empty
    # keys appear out of nowhere.
    if f.alias:
        result["alias"] = f.alias
    if f.coordinate:
        result["coordinate"] = f.coordinate
    return result


def _toolchain_finding(f: ToolchainFinding) -> dict[str, Any]:
    result: dict[str, Any] = {
        "rule_id": f.rule_id,
        "severity": f.severity.value,
        "common_severity": f.severity.to_common().value,
        "message": f.message,
    }
    if f.detail:
        result["detail"] = f.detail
    if f.recommendation:
        result["recommendation"] = f.recommendation
    return result


def _library_health_finding(f: LibraryHealthFinding) -> dict[str, Any]:
    result: dict[str, Any] = {
        "alias": f.alias,
        "coordinate": f.coordinate,
        "version": f.version,
        "signal": f.signal.value,
        "severity": f.severity.value,
        "common_severity": f.severity.to_common().value,
        "message": f.message,
    }
    if f.replacement:
        result["replacement"] = f.replacement
    if f.migration_url:
        result["migration_url"] = f.migration_url
    if f.days_since_release is not None:
        result["days_since_release"] = f.days_since_release
    return result


def _changelog_entry(e: ChangelogEntry) -> dict[str, Any]:
    result: dict[str, Any] = {
        "alias": e.alias,
        "coordinate": e.coordinate,
        "pinned_version": e.pinned_version,
        "latest_version": e.latest_version,
        "breaking_signal": e.breaking_signal.value,
    }
    if e.changelog_url:
        result["changelog_url"] = e.changelog_url
    if e.snippet:
        result["snippet"] = e.snippet
    return result


def _module_usage_map(usage_map: ModuleUsageMap | None) -> dict[str, Any] | None:
    if usage_map is None:
        return None
    return {
        "modules_scanned": usage_map.modules_scanned,
        "library_usages": [
            {
                "alias": u.alias,
                "coordinate": u.coordinate,
                "implementation_count": len(u.implementation_modules),
                "api_count": u.api_count,
                "test_count": len(u.test_modules),
                "direct_count": u.direct_count,
                "implementation_modules": list(u.implementation_modules),
                "api_modules": list(u.api_modules),
                "test_modules": list(u.test_modules),
            }
            for u in usage_map.libraries_in_use()
        ],
        "top_modules": [
            {"module_path": m.module_path, "direct_dep_count": m.direct_dep_count}
            for m in usage_map.top_modules(10)
        ],
    }


def _finding(f: Finding) -> dict[str, Any]:
    result: dict[str, Any] = {
        "rule_id": f.rule_id,
        "severity": f.severity.value,
        "common_severity": f.severity.to_common().value,
        "message": f.message,
    }
    if f.details:
        result["details"] = f.details
    return result


def _risk_score(rsr: RiskScoreReport | None) -> dict[str, Any] | None:
    if rsr is None:
        return None
    return {
        "libraries_scored": rsr.libraries_scored,
        "avg_score": round(rsr.avg_score, 1),
        "max_score": rsr.max_score,
        "critical_count": rsr.critical_count,
        "high_count": rsr.high_count,
        "weights": {
            "outdatedness": rsr.weights.outdatedness,
            "cve": rsr.weights.cve,
            "abandonment": rsr.weights.abandonment,
            "blast_radius": rsr.weights.blast_radius,
            "compliance": rsr.weights.compliance,
            "license": rsr.weights.license,
        },
        "thresholds": {
            "critical": rsr.thresholds.critical,
            "high": rsr.thresholds.high,
            "medium": rsr.thresholds.medium,
        },
        "top_libraries": [
            {
                "alias": lib.alias,
                "coordinate": lib.coordinate,
                "version": lib.version,
                "total_score": lib.total_score,
                "level": lib.level.value,
                "breakdown": [
                    {
                        "dimension": d.name,
                        "score": d.score,
                        "cap": d.cap,
                        "detail": d.detail,
                    }
                    for d in lib.breakdown
                ],
            }
            for lib in rsr.top
        ],
    }


def _license_audit(audit: LicenseAudit | None) -> dict[str, Any] | None:
    if audit is None:
        return None
    return {
        "libraries_audited": audit.libraries_audited,
        "flagged_count": audit.flagged_count,
        "permissive_count": audit.permissive_count,
        "has_violations": audit.has_violations,
        "findings": [
            {
                "alias": f.alias,
                "coordinate": f.coordinate,
                "version": f.version,
                "tier": f.tier.value,
                "license_name": f.license_name,
                "license_url": f.license_url,
            }
            for f in audit.findings
        ],
    }
