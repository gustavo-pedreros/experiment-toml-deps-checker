"""Markdown report writer."""

from __future__ import annotations

from pathlib import Path

from gradle_deps_monitor.domain import FreezeReport
from gradle_deps_monitor.domain.advisory import AdvisorySeverity, LibraryAdvisory
from gradle_deps_monitor.domain.bom import BomResolution, VersionSource
from gradle_deps_monitor.domain.catalog import Bundle, Library, Plugin
from gradle_deps_monitor.domain.changelog import BreakingSignal, ChangelogEntry
from gradle_deps_monitor.domain.compliance import ComplianceFinding, ComplianceSeverity
from gradle_deps_monitor.domain.finding import Finding, Severity
from gradle_deps_monitor.domain.library_health import LibraryHealthFinding, LibraryHealthSeverity
from gradle_deps_monitor.domain.license import LicenseAudit, LicenseTier
from gradle_deps_monitor.domain.module_usage import ModuleUsageMap
from gradle_deps_monitor.domain.risk_score import RiskLevel, RiskScoreReport
from gradle_deps_monitor.domain.toolchain import ToolchainFinding, ToolchainSeverity
from gradle_deps_monitor.domain.version_status import LibraryVersionStatus, VersionDrift


class MarkdownWriter:
    """Serialises a :class:`~gradle_deps_monitor.domain.FreezeReport` to Markdown."""

    def write(self, report: FreezeReport, dest: Path) -> None:
        """Write *report* to *dest*, creating parent directories as needed."""
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(_render(report), encoding="utf-8")


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------

_SEVERITY_ICON = {
    Severity.ERROR: "🔴",
    Severity.WARNING: "⚠️",
    Severity.INFO: "\U00002139️",
    Severity.SUGGESTION: "💡",
}


def _render(report: FreezeReport) -> str:
    cat = report.catalog
    libs = sorted(cat.libraries, key=lambda lib: lib.alias)
    plugins = sorted(cat.plugins, key=lambda p: p.alias)
    bundles = sorted(cat.bundles, key=lambda b: b.alias)
    status_by_alias = {s.alias: s for s in report.library_version_statuses}

    sections: list[str] = [
        _header(report),
        _outdated_summary_section(report),
        _bom_section(report),
        _libraries_section(libs, status_by_alias, report.bom_resolutions),
        _plugins_section(plugins),
        _bundles_section(bundles),
        _health_section(list(report.health_findings)),
        _security_section(list(report.vulnerable_libraries)),
        _compliance_section(list(report.compliance_findings)),
        _toolchain_section(list(report.toolchain_findings)),
        _library_health_section(list(report.library_health_findings)),
        _changelog_section(list(report.changelog_entries)),
        _module_usage_section(report.module_usage_map),
        _license_section(report.license_audit),
        _risk_score_section(report.risk_score_report),
    ]
    return "\n\n".join(s for s in sections if s) + "\n"


def _header(report: FreezeReport) -> str:
    cat = report.catalog
    ts = report.generated_at.isoformat(timespec="seconds")
    return (
        "# Gradle Dependency Freeze Report\n\n"
        f"- **Generated:** {ts}\n"
        f"- **Catalog:** `{cat.source_path}`\n"
        f"- **Libraries:** {cat.library_count} | "
        f"**Plugins:** {cat.plugin_count} | "
        f"**Bundles:** {len(cat.bundles)}"
    )


def _libraries_section(
    libs: list[Library],
    status_by_alias: dict[str, LibraryVersionStatus] | None = None,
    bom_resolutions: tuple[BomResolution, ...] = (),
) -> str:
    if not libs:
        return ""
    status_by_alias = status_by_alias or {}
    bom_versions: dict[str, str] = {b.bom_alias: b.bom_version.raw for b in bom_resolutions}

    def _drift_cell(alias: str) -> str:
        status = status_by_alias.get(alias)
        if status is None or status.drift in (VersionDrift.NONE, VersionDrift.UNKNOWN):
            return _DRIFT_LABEL[status.drift] if status else "—"
        latest = status.latest.raw if status.latest else "?"
        return f"{_DRIFT_LABEL[status.drift]} → `{latest}`"

    def _source_cell(lib: Library) -> str:
        if lib.version_source == VersionSource.FROM_BOM and lib.bom_alias:
            bom_v = bom_versions.get(lib.bom_alias, "?")
            return f"via `{lib.bom_alias}` `{bom_v}`"
        if lib.version_source == VersionSource.VERSION_REF:
            return f"ref `{lib.version_ref}`"
        if lib.version_source == VersionSource.UNRESOLVED:
            return "**unresolved**"
        return "—"

    rows = "\n".join(
        f"| `{lib.alias}` | `{lib.group}` | `{lib.artifact}` "
        f"| `{lib.version}` | {lib.version.stability} "
        f"| {_drift_cell(lib.alias)} | {_source_cell(lib)} |"
        for lib in libs
    )
    return (
        f"## Libraries ({len(libs)})\n\n"
        "| Alias | Group | Artifact | Version | Stability | Drift | Source |\n"
        "|---|---|---|---|---|---|---|\n"
        f"{rows}"
    )


def _bom_section(report: FreezeReport) -> str:
    if not report.bom_resolutions:
        return ""
    lines = []
    for res in report.bom_resolutions:
        managed_count = len(res.managed)
        children = sorted(
            lib.alias for lib in report.catalog.libraries if lib.bom_alias == res.bom_alias
        )
        children_text = (
            ", ".join(f"`{a}`" for a in children)
            if children
            else "_no managed children in this catalog_"
        )
        lines.append(
            f"### `{res.bom_alias}` — `{res.bom_coordinate}` `{res.bom_version}`\n"
            f"- Manages **{managed_count}** coordinate(s).\n"
            f"- Children in catalog: {children_text}"
        )
    return f"## BoMs ({len(report.bom_resolutions)})\n\n" + "\n\n".join(lines)


_DRIFT_LABEL: dict[VersionDrift, str] = {
    VersionDrift.NONE: "—",
    VersionDrift.PATCH: "patch",
    VersionDrift.MINOR: "minor",
    VersionDrift.MAJOR: "**major**",
    VersionDrift.UNKNOWN: "unknown",
}


def _outdated_summary_section(report: FreezeReport) -> str:
    if not report.library_version_statuses:
        return ""
    total = len(report.library_version_statuses)
    if total == 0:
        return ""
    parts = [
        f"**{report.major_outdated_count}** major-behind",
        f"**{report.minor_outdated_count}** minor-behind",
        f"**{report.patch_outdated_count}** patch-behind",
    ]
    unknown = sum(1 for s in report.library_version_statuses if s.drift == VersionDrift.UNKNOWN)
    if unknown:
        parts.append(f"**{unknown}** unknown")
    return "## Outdated summary\n\n" + ", ".join(parts) + f" out of {total} libraries."


def _plugins_section(plugins: list[Plugin]) -> str:
    if not plugins:
        return ""
    rows = "\n".join(
        f"| `{p.alias}` | `{p.id}` | `{p.version}` | {p.version.stability} |" for p in plugins
    )
    return (
        f"## Plugins ({len(plugins)})\n\n"
        "| Alias | ID | Version | Stability |\n"
        "|---|---|---|---|\n"
        f"{rows}"
    )


def _bundles_section(bundles: list[Bundle]) -> str:
    if not bundles:
        return ""
    rows = "\n".join(
        f"| `{b.alias}` | {', '.join(f'`{m}`' for m in sorted(b.member_aliases))} |"
        for b in bundles
    )
    return f"## Bundles ({len(bundles)})\n\n| Alias | Members |\n|---|---|\n{rows}"


_ADVISORY_SEVERITY_ICON: dict[AdvisorySeverity, str] = {
    AdvisorySeverity.CRITICAL: "🔴",
    AdvisorySeverity.HIGH: "🟠",
    AdvisorySeverity.MEDIUM: "🟡",
    AdvisorySeverity.LOW: "🔵",
    AdvisorySeverity.UNKNOWN: "⚪",
}


def _security_section(vulnerable: list[LibraryAdvisory]) -> str:
    if not vulnerable:
        return ""
    rows: list[str] = []
    for la in sorted(vulnerable, key=lambda x: x.alias):
        for adv in sorted(la.advisories, key=lambda a: a.severity):
            icon = _ADVISORY_SEVERITY_ICON.get(adv.severity, "⚪")
            cve = f" / {adv.cve_id}" if adv.cve_id else ""
            fixed = f" · fixed in `{adv.fixed_version}`" if adv.fixed_version else ""
            rows.append(
                f"| `{la.alias}` | `{la.version}` | {icon} {adv.severity.upper()}"
                f" | {adv.ghsa_id}{cve}{fixed} — {adv.summary}"
                f" | [advisory]({adv.url}) |"
            )
    noun = "library" if len(vulnerable) == 1 else "libraries"
    return (
        f"## Security ({len(vulnerable)} vulnerable {noun})\n\n"
        "> ⚠️ The following libraries have known security advisories for the "
        "versions pinned in this catalog.\n\n"
        "| Alias | Version | Severity | Advisory | Link |\n"
        "|---|---|---|---|---|\n" + "\n".join(rows)
    )


_COMPLIANCE_SEVERITY_ICON: dict[ComplianceSeverity, str] = {
    ComplianceSeverity.ERROR: "🔴",
    ComplianceSeverity.WARNING: "⚠️",
    ComplianceSeverity.INFO: "✅",
}


def _compliance_section(findings: list[ComplianceFinding]) -> str:
    if not findings:
        return ""
    rows: list[str] = []
    for f in findings:
        icon = _COMPLIANCE_SEVERITY_ICON.get(f.severity, "")
        deadline = f" (deadline: {f.deadline})" if f.deadline else ""
        migration = f" → `{f.migration}`" if f.migration else ""
        # RFC-0015: per-library findings carry an alias; catalog-level
        # findings (e.g. targetSdk deadline) leave the column empty.
        library_cell = f"`{f.alias}`" if f.alias else "—"
        rows.append(
            f"| {icon} {f.severity.upper()} | `{f.rule_id}` | "
            f"{library_cell} | {f.message}{deadline}{migration} |"
        )
    noun = "finding" if len(findings) == 1 else "findings"
    return (
        f"## Play Store Compliance ({len(findings)} {noun})\n\n"
        "> Checked against the bundled Play Store compliance knowledge base.\n\n"
        "| Severity | Rule | Library | Details |\n"
        "|---|---|---|---|\n" + "\n".join(rows)
    )


_TOOLCHAIN_SEVERITY_ICON: dict[ToolchainSeverity, str] = {
    ToolchainSeverity.ERROR: "🔴",
    ToolchainSeverity.WARNING: "⚠️",
    ToolchainSeverity.INFO: "✅",
}


def _toolchain_section(findings: list[ToolchainFinding]) -> str:
    if not findings:
        return ""
    rows: list[str] = []
    for f in findings:
        icon = _TOOLCHAIN_SEVERITY_ICON.get(f.severity, "")
        rec = f" {f.recommendation}" if f.recommendation else ""
        rows.append(f"| {icon} {f.severity.upper()} | `{f.rule_id}` | {f.message}{rec} |")
    noun = "finding" if len(findings) == 1 else "findings"
    return (
        f"## Toolchain Compatibility ({len(findings)} {noun})\n\n"
        "> Checked against the bundled toolchain compatibility matrices.\n\n"
        "| Severity | Rule | Details |\n"
        "|---|---|---|\n" + "\n".join(rows)
    )


def _health_section(findings: list[Finding]) -> str:
    if not findings:
        return ""
    rows = "\n".join(
        f"| {_SEVERITY_ICON.get(f.severity, f.severity.value)} {f.severity.value} "
        f"| `{f.rule_id}` | {f.message} |"
        for f in findings
    )
    return (
        f"## Catalog Health ({len(findings)} finding(s))\n\n"
        "| Severity | Rule | Message |\n"
        "|---|---|---|\n"
        f"{rows}"
    )


_BREAKING_SIGNAL_ICON: dict[BreakingSignal, str] = {
    BreakingSignal.LIKELY: "🔴",
    BreakingSignal.CLEAN: "🟢",
    BreakingSignal.UNKNOWN: "⚪",
}


def _changelog_section(entries: list[ChangelogEntry]) -> str:
    if not entries:
        return ""
    rows: list[str] = []
    for e in sorted(entries, key=lambda x: x.alias):
        icon = _BREAKING_SIGNAL_ICON.get(e.breaking_signal, "⚪")
        link = f" [release notes]({e.changelog_url})" if e.changelog_url else ""
        snippet = f" — _{e.snippet}_" if e.snippet else ""
        rows.append(
            f"| `{e.alias}` | `{e.coordinate}` | `{e.pinned_version}` "
            f"| `{e.latest_version}` | {icon} {e.breaking_signal.upper()}"
            f" |{link}{snippet} |"
        )
    noun = "upgrade" if len(entries) == 1 else "upgrades"
    return (
        f"## Major Upgrades ({len(entries)} {noun} available)\n\n"
        "> Breaking-change signal is a heuristic based on release note keywords.\n\n"
        "| Alias | Coordinate | Pinned | Latest | Breaking? | Notes |\n"
        "|---|---|---|---|---|---|\n" + "\n".join(rows)
    )


_LIBRARY_HEALTH_SEVERITY_ICON: dict[LibraryHealthSeverity, str] = {
    LibraryHealthSeverity.HIGH: "🔴",
    LibraryHealthSeverity.MEDIUM: "🟡",
    LibraryHealthSeverity.LOW: "🔵",
}


def _library_health_section(findings: list[LibraryHealthFinding]) -> str:
    if not findings:
        return ""
    rows: list[str] = []
    for f in sorted(findings, key=lambda x: (x.severity, x.alias)):
        icon = _LIBRARY_HEALTH_SEVERITY_ICON.get(f.severity, "⚪")
        replacement = f" → `{f.replacement}`" if f.replacement else ""
        migration = f" ([migration]({f.migration_url}))" if f.migration_url else ""
        rows.append(
            f"| {icon} {f.severity.upper()} | `{f.alias}` | `{f.coordinate}` "
            f"| `{f.version}` | {f.signal.upper()} | {f.message}{replacement}{migration} |"
        )
    noun = "finding" if len(findings) == 1 else "findings"
    return (
        f"## Library Health ({len(findings)} {noun})\n\n"
        "> Detected via curated knowledge base, Maven POM relocation tags, "
        "and inactivity heuristics.\n\n"
        "| Severity | Alias | Coordinate | Version | Signal | Details |\n"
        "|---|---|---|---|---|---|\n" + "\n".join(rows)
    )


_MODULE_USAGE_TOP_N = 10


def _module_usage_section(usage_map: ModuleUsageMap | None) -> str:
    if usage_map is None:
        return ""
    in_use = list(usage_map.libraries_in_use())
    if not in_use:
        return (
            f"## Module Usage Map ({usage_map.modules_scanned} modules scanned)\n\n"
            "> No catalog libraries were referenced in the scanned build files."
        )

    # --- per-library table (only libraries with at least one usage) ---
    lib_rows = "\n".join(
        f"| `{u.alias}` | `{u.coordinate}` "
        f"| {len(u.implementation_modules)} "
        f"| {u.api_count} "
        f"| {u.test_only_count} |"
        for u in sorted(in_use, key=lambda x: (-x.direct_count, x.alias))
    )
    lib_table = (
        "### Libraries with usage\n\n"
        "| Alias | Coordinate | impl | api | test only |\n"
        "|---|---|---|---|---|\n"
        f"{lib_rows}"
    )

    # --- top-N modules table ---
    top = list(usage_map.top_modules(_MODULE_USAGE_TOP_N))
    mod_rows = "\n".join(f"| `{m.module_path}` | {m.direct_dep_count} |" for m in top)
    top_label = f"Top {len(top)}" if len(top) == _MODULE_USAGE_TOP_N else f"{len(top)}"
    mod_table = (
        f"### {top_label} modules by direct dependency count\n\n"
        "| Module | Direct deps |\n"
        "|---|---|\n"
        f"{mod_rows}"
    )

    scanned = usage_map.modules_scanned
    return (
        f"## Module Usage Map ({scanned} {'module' if scanned == 1 else 'modules'} scanned)\n\n"
        "> Static analysis of `build.gradle(.kts)` files. "
        "Only the dotted-accessor form (`libs.foo.bar`) is matched.\n\n"
        f"{lib_table}\n\n"
        f"{mod_table}"
    )


_LICENSE_TIER_ICON: dict[LicenseTier, str] = {
    LicenseTier.PERMISSIVE: "✅",
    LicenseTier.WEAK_COPYLEFT: "⚠️",
    LicenseTier.STRONG_COPYLEFT: "🔴",
    LicenseTier.UNKNOWN: "❓",
}


def _license_section(audit: LicenseAudit | None) -> str:
    if audit is None:
        return ""

    n = audit.libraries_audited
    header = f"## License Audit ({n} {'library' if n == 1 else 'libraries'} audited)"

    if not audit.findings:
        permissive = audit.permissive_count
        return (
            f"{header}\n\n"
            f"> ✅ All {permissive} {'library' if permissive == 1 else 'libraries'} "
            "use permissive licenses."
        )

    rows = "\n".join(
        f"| {_LICENSE_TIER_ICON.get(f.tier, '❓')} {f.tier.value.replace('_', ' ').title()} "
        f"| `{f.alias}` | `{f.coordinate}` | `{f.version}` "
        f"| {f.license_name or '_(not declared)_'} |"
        for f in audit.findings
    )
    permissive_line = (
        f"\n\n> ✅ {audit.permissive_count} other "
        f"{'library' if audit.permissive_count == 1 else 'libraries'} use permissive licenses."
        if audit.permissive_count > 0
        else ""
    )
    return (
        f"{header}\n\n"
        "> License tiers: ✅ Permissive · ⚠️ Weak copyleft · 🔴 Strong copyleft · ❓ Unknown\n\n"
        "| Tier | Alias | Coordinate | Version | License |\n"
        "|---|---|---|---|---|\n"
        f"{rows}"
        f"{permissive_line}"
    )


_RISK_LEVEL_ICON: dict[RiskLevel, str] = {
    RiskLevel.CRITICAL: "🔴",
    RiskLevel.HIGH: "🟠",
    RiskLevel.MEDIUM: "🟡",
    RiskLevel.LOW: "🔵",
    RiskLevel.NONE: "⚪",
}

_BAR_FULL = "█"
_BAR_EMPTY = "░"
_BAR_WIDTH = 15


def _bar(score: int, cap: int) -> str:
    """Render a compact ASCII progress bar showing *score* out of *cap*."""
    if cap == 0:
        return _BAR_EMPTY * _BAR_WIDTH
    filled = round(_BAR_WIDTH * score / cap)
    return _BAR_FULL * filled + _BAR_EMPTY * (_BAR_WIDTH - filled)


def _risk_score_section(rsr: RiskScoreReport | None) -> str:
    if rsr is None:
        return ""

    n = rsr.libraries_scored
    top = rsr.top
    header = (
        f"## Risk Score (top {len(top)} of {n} "
        f"{'library' if n == 1 else 'libraries'} · experimental)"
    )
    disclaimer = (
        "> ⚠️ **Experimental.** Scores are most meaningful when compared across "
        "multiple freeze reports — a single number in isolation is less informative "
        "than the trend over time."
    )

    if not top:
        return f"{header}\n\n{disclaimer}\n\n> ✅ No risk signals detected."

    blocks: list[str] = [header, "", disclaimer, ""]

    for i, lib in enumerate(top, 1):
        icon = _RISK_LEVEL_ICON.get(lib.level, "⚪")
        blocks.append(
            f"### #{i} `{lib.alias}` — {lib.coordinate} `{lib.version}`  "
            f"**Score {lib.total_score}** {icon} {lib.level.upper()}"
        )
        rows = "\n".join(
            f"| {d.name} | {_bar(d.score, d.cap)} | {d.score} / {d.cap} | {d.detail} |"
            for d in lib.breakdown
        )
        blocks.append(f"| Dimension | Bar | Score | Detail |\n|---|---|---|---|\n{rows}")

    return "\n".join(blocks)
