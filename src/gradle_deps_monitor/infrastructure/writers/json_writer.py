"""JSON report writer."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from gradle_deps_monitor.domain import FreezeReport
from gradle_deps_monitor.domain.advisory import Advisory, LibraryAdvisory
from gradle_deps_monitor.domain.catalog import Bundle, Library, Plugin
from gradle_deps_monitor.domain.compliance import ComplianceFinding
from gradle_deps_monitor.domain.finding import Finding


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

    return {
        "schema_version": "1",
        "generated_at": report.generated_at.isoformat(timespec="seconds"),
        "catalog": {
            "source_path": str(cat.source_path),
            "library_count": cat.library_count,
            "plugin_count": cat.plugin_count,
            "bundle_count": len(cat.bundles),
            "libraries": [_lib(lib) for lib in libs],
            "plugins": [_plugin(p) for p in plugins],
            "bundles": [_bundle(b) for b in bundles],
        },
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
    }


def _lib(lib: Library) -> dict[str, Any]:
    return {
        "alias": lib.alias,
        "group": lib.group,
        "artifact": lib.artifact,
        "version": str(lib.version),
        "stability": lib.version.stability.value,
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
        "message": f.message,
    }
    if f.detail:
        result["detail"] = f.detail
    if f.deadline:
        result["deadline"] = f.deadline
    if f.migration:
        result["migration"] = f.migration
    return result


def _finding(f: Finding) -> dict[str, Any]:
    result: dict[str, Any] = {
        "rule_id": f.rule_id,
        "severity": f.severity.value,
        "message": f.message,
    }
    if f.details:
        result["details"] = f.details
    return result
