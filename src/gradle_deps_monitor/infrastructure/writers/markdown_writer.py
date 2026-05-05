"""Markdown report writer."""

from __future__ import annotations

from pathlib import Path

from gradle_deps_monitor.domain import FreezeReport
from gradle_deps_monitor.domain.advisory import AdvisorySeverity, LibraryAdvisory
from gradle_deps_monitor.domain.catalog import Bundle, Library, Plugin
from gradle_deps_monitor.domain.changelog import BreakingSignal, ChangelogEntry
from gradle_deps_monitor.domain.compliance import ComplianceFinding, ComplianceSeverity
from gradle_deps_monitor.domain.finding import Finding, Severity
from gradle_deps_monitor.domain.library_health import LibraryHealthFinding, LibraryHealthSeverity
from gradle_deps_monitor.domain.toolchain import ToolchainFinding, ToolchainSeverity


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

    sections: list[str] = [
        _header(report),
        _libraries_section(libs),
        _plugins_section(plugins),
        _bundles_section(bundles),
        _health_section(list(report.health_findings)),
        _security_section(list(report.vulnerable_libraries)),
        _compliance_section(list(report.compliance_findings)),
        _toolchain_section(list(report.toolchain_findings)),
        _library_health_section(list(report.library_health_findings)),
        _changelog_section(list(report.changelog_entries)),
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


def _libraries_section(libs: list[Library]) -> str:
    if not libs:
        return ""
    rows = "\n".join(
        f"| `{lib.alias}` | `{lib.group}` | `{lib.artifact}` "
        f"| `{lib.version}` | {lib.version.stability} |"
        for lib in libs
    )
    return (
        f"## Libraries ({len(libs)})\n\n"
        "| Alias | Group | Artifact | Version | Stability |\n"
        "|---|---|---|---|---|\n"
        f"{rows}"
    )


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
        rows.append(
            f"| {icon} {f.severity.upper()} | `{f.rule_id}` | {f.message}{deadline}{migration} |"
        )
    noun = "finding" if len(findings) == 1 else "findings"
    return (
        f"## Play Store Compliance ({len(findings)} {noun})\n\n"
        "> Checked against the bundled Play Store compliance knowledge base.\n\n"
        "| Severity | Rule | Details |\n"
        "|---|---|---|\n" + "\n".join(rows)
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
