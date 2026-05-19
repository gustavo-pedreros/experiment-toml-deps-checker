"""Console executive summaries rendered with Rich."""

from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from gradle_deps_monitor.domain import FreezeReport, Severity
from gradle_deps_monitor.domain.advisory import AdvisorySeverity
from gradle_deps_monitor.domain.changelog import BreakingSignal
from gradle_deps_monitor.domain.compliance import ComplianceSeverity
from gradle_deps_monitor.domain.diff import FreezeDiff
from gradle_deps_monitor.domain.library_health import LibraryHealthSeverity
from gradle_deps_monitor.domain.license import LicenseTier
from gradle_deps_monitor.domain.risk_score import RiskLevel, RiskScoreReport
from gradle_deps_monitor.domain.severity import HasCommonSeverity
from gradle_deps_monitor.domain.severity_style import style_for
from gradle_deps_monitor.domain.toolchain import ToolchainSeverity
from gradle_deps_monitor.domain.version import Stability
from gradle_deps_monitor.domain.version_status import VersionDrift


def _rich_style(severity: HasCommonSeverity) -> str:
    """Resolve any section-specific severity to its unified Rich style.

    The parameter is the structural :class:`HasCommonSeverity` protocol so the
    helper accepts every domain severity enum without enumerating the union
    by hand. Rendering goes through :mod:`severity_style.STYLE` so the same
    severity displays identically in console, Markdown, and Slack
    (RFC-0016b).
    """
    return style_for(severity.to_common()).rich_style


_SEVERITY_LABEL: dict[Severity, str] = {
    Severity.ERROR: "error",
    Severity.WARNING: "warning",
    Severity.INFO: "info",
    Severity.SUGGESTION: "suggestion",
}


def print_summary(
    report: FreezeReport,
    written_files: tuple[Path, ...],
    *,
    console: Console | None = None,
) -> None:
    """Print an executive summary of *report* to the console using Rich.

    :param report: The generated freeze report.
    :param written_files: Paths of every file that was written.
    :param console: Optional Rich :class:`~rich.console.Console` instance
        (defaults to stdout). Inject a different console in tests.
    """
    con = console or Console()
    cat = report.catalog
    ts = report.generated_at.isoformat(timespec="seconds")

    # --- Stats panel ---
    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="bold")
    grid.add_column()
    grid.add_row("Generated", ts)
    grid.add_row("Libraries", str(cat.library_count))
    grid.add_row("Plugins", str(cat.plugin_count))
    grid.add_row("Bundles", str(len(cat.bundles)))
    con.print(Panel(grid, title="[bold]Gradle Dependency Freeze Report[/bold]", expand=False))

    # --- BoMs ---
    if report.bom_resolutions:
        con.print()
        con.print(f"[bold]BoMs ({len(report.bom_resolutions)})[/bold]")
        for res in report.bom_resolutions:
            children = sum(1 for lib in cat.libraries if lib.bom_alias == res.bom_alias)
            con.print(
                f"  • [cyan]{res.bom_alias}[/cyan]  {res.bom_version}  "
                f"[dim]manages {len(res.managed)}, catalog uses {children}[/dim]"
            )

    # --- Outdated summary ---
    if report.library_version_statuses:
        outdated = report.outdated_libraries
        # Issue #12: align with the Markdown writer's outdated summary,
        # which includes libraries whose drift is UNKNOWN (e.g. resolved
        # against a non-standard repository). Pre-fix the console total
        # silently excluded them.
        unknown_count = sum(
            1 for s in report.library_version_statuses if s.drift == VersionDrift.UNKNOWN
        )
        con.print()
        if outdated or unknown_count:
            total = len(outdated) + unknown_count
            con.print(f"[bold yellow]Outdated ({total})[/bold yellow]")
            breakdown = [
                f"[red]{report.major_outdated_count} major[/red]",
                f"[yellow]{report.minor_outdated_count} minor[/yellow]",
                f"[dim]{report.patch_outdated_count} patch[/dim]",
            ]
            if unknown_count:
                breakdown.append(f"[dim]{unknown_count} unknown[/dim]")
            con.print("  " + "  ".join(breakdown))
        else:
            con.print("[green]Versions[/green] — all libraries up to date")

    # --- Non-stable versions ---
    non_stable = sorted(
        (lib for lib in cat.libraries if lib.version.stability is not Stability.STABLE),
        key=lambda lib: lib.alias,
    )
    if non_stable:
        con.print()
        con.print(f"[bold yellow]Non-stable versions ({len(non_stable)})[/bold yellow]")
        for lib in non_stable:
            con.print(
                f"  • [cyan]{lib.alias}[/cyan]  {lib.version}  [dim]({lib.version.stability})[/dim]"
            )

    # --- Catalog health ---
    con.print()
    if report.health_findings:
        count = len(report.health_findings)
        con.print(f"[bold]Catalog Health[/bold] — {count} finding(s)")
        for finding in report.health_findings:
            style = _rich_style(finding.severity)
            label = _SEVERITY_LABEL.get(finding.severity, finding.severity.value)
            con.print(
                f"  [{style}]{label}[/{style}]  [dim]{finding.rule_id}[/dim]  {finding.message}"
            )
    else:
        con.print("[green]Catalog Health[/green] — no issues found")

    # --- Security advisories ---
    if report.security_advisories:
        con.print()
        vulnerable = report.vulnerable_libraries
        if not vulnerable:
            con.print("[green]Security[/green] — no known vulnerabilities")
        else:
            critical = sum(1 for la in vulnerable if la.has_critical)
            high = sum(1 for la in vulnerable if la.has_high)
            # RFC-0028: enumerate every populated severity bucket
            # explicitly. Pre-fix anything-non-critical-non-high was
            # collapsed to ``N other``, hiding the medium/low split.
            # Bucket each library by its max severity so the counts
            # partition the vulnerable set.
            medium = sum(1 for la in vulnerable if la.max_severity == AdvisorySeverity.MEDIUM)
            low = sum(1 for la in vulnerable if la.max_severity == AdvisorySeverity.LOW)
            parts: list[str] = []
            if critical:
                parts.append(f"[bold red]{critical} critical[/bold red]")
            if high:
                parts.append(f"[bold yellow]{high} high[/bold yellow]")
            if medium:
                parts.append(f"[yellow]{medium} medium[/yellow]")
            if low:
                parts.append(f"[blue]{low} low[/blue]")
            con.print(f"[bold]Security[/bold] — {len(vulnerable)} vulnerable: {', '.join(parts)}")
            for la in sorted(vulnerable, key=lambda x: x.alias):
                sev = la.max_severity
                style = _rich_style(sev) if sev else "dim"
                label = sev.value.upper() if sev else "unknown"
                con.print(
                    f"  [{style}]{label}[/{style}]  [cyan]{la.alias}[/cyan]"
                    f"  {la.version}  [dim]({len(la.advisories)} advisory)[/dim]"
                )

    # --- Play Store compliance ---
    if report.compliance_findings:
        con.print()
        violations = sum(
            1 for cf in report.compliance_findings if cf.severity == ComplianceSeverity.ERROR
        )
        comp_warnings = sum(
            1 for cf in report.compliance_findings if cf.severity == ComplianceSeverity.WARNING
        )
        comp_parts: list[str] = []
        if violations:
            comp_parts.append(f"[bold red]{violations} violation(s)[/bold red]")
        if comp_warnings:
            comp_parts.append(f"[bold yellow]{comp_warnings} warning(s)[/bold yellow]")
        comp_label = ", ".join(comp_parts) if comp_parts else "informational"
        con.print(
            f"[bold]Play Store Compliance[/bold] — "
            f"{len(report.compliance_findings)} finding(s): {comp_label}"
        )
        for cf in report.compliance_findings:
            cf_style = _rich_style(cf.severity)
            cf_label = cf.severity.value.upper()
            migration = f"  → [cyan]{cf.migration}[/cyan]" if cf.migration else ""
            con.print(
                f"  [{cf_style}]{cf_label}[/{cf_style}]  "
                f"[dim]{cf.rule_id}[/dim]  {cf.message}{migration}"
            )

    # --- Toolchain compatibility ---
    if report.toolchain_findings:
        con.print()
        tc_errors = sum(
            1 for tf in report.toolchain_findings if tf.severity == ToolchainSeverity.ERROR
        )
        tc_warnings = sum(
            1 for tf in report.toolchain_findings if tf.severity == ToolchainSeverity.WARNING
        )
        tc_parts: list[str] = []
        if tc_errors:
            tc_parts.append(f"[bold red]{tc_errors} error(s)[/bold red]")
        if tc_warnings:
            tc_parts.append(f"[bold yellow]{tc_warnings} warning(s)[/bold yellow]")
        tc_label = ", ".join(tc_parts) if tc_parts else "informational"
        con.print(
            f"[bold]Toolchain Compatibility[/bold] — "
            f"{len(report.toolchain_findings)} finding(s): {tc_label}"
        )
        for tf in report.toolchain_findings:
            tf_style = _rich_style(tf.severity)
            tf_label = tf.severity.value.upper()
            con.print(
                f"  [{tf_style}]{tf_label}[/{tf_style}]  [dim]{tf.rule_id}[/dim]  {tf.message}"
            )
            if tf.recommendation:
                con.print(f"    [dim]→ {tf.recommendation}[/dim]")

    # --- Library health ---
    if report.library_health_findings:
        con.print()
        lh_high = sum(
            1 for lh in report.library_health_findings if lh.severity == LibraryHealthSeverity.HIGH
        )
        lh_medium = sum(
            1
            for lh in report.library_health_findings
            if lh.severity == LibraryHealthSeverity.MEDIUM
        )
        lh_parts: list[str] = []
        if lh_high:
            lh_parts.append(f"[bold red]{lh_high} high[/bold red]")
        if lh_medium:
            lh_parts.append(f"[bold yellow]{lh_medium} medium[/bold yellow]")
        lh_label = ", ".join(lh_parts) if lh_parts else "informational"
        con.print(
            f"[bold]Library Health[/bold] — "
            f"{len(report.library_health_findings)} finding(s): {lh_label}"
        )
        for lh in sorted(report.library_health_findings, key=lambda f: (f.severity, f.alias)):
            lh_style = _rich_style(lh.severity)
            lh_sev_label = lh.severity.value.upper()
            replacement = f"  → [cyan]{lh.replacement}[/cyan]" if lh.replacement else ""
            con.print(
                f"  [{lh_style}]{lh_sev_label}[/{lh_style}]  "
                f"[cyan]{lh.alias}[/cyan]  [dim]({lh.signal.upper()})[/dim]"
                f"  {lh.message}{replacement}"
            )

    # --- Major upgrades / changelog ---
    if report.changelog_entries:
        con.print()
        breaking = sum(
            1 for e in report.changelog_entries if e.breaking_signal == BreakingSignal.LIKELY
        )
        ch_parts: list[str] = []
        if breaking:
            ch_parts.append(f"[bold red]{breaking} likely breaking[/bold red]")
        remaining = len(report.changelog_entries) - breaking
        if remaining:
            ch_parts.append(f"{remaining} other")
        ch_label = ", ".join(ch_parts) if ch_parts else "no breaking signals"
        con.print(
            f"[bold]Major Upgrades[/bold] — {len(report.changelog_entries)} available: {ch_label}"
        )
        # RFC-0024 PR #2: surface silent scraper degradation when the
        # GitHub rate limit was hit during this run.
        cs = report.changelog_stats
        if cs.is_degraded:
            con.print(
                f"  [bold yellow]⚠ {cs.fetched} of {cs.attempted}[/bold yellow] "
                f"release notes fetched; [bold yellow]{cs.rate_limited}[/bold yellow] "
                "fell back to repo URL (GitHub rate limit — set "
                "[cyan]GITHUB_TOKEN[/cyan] for full coverage)."
            )
        for entry in sorted(report.changelog_entries, key=lambda e: e.alias):
            if entry.breaking_signal == BreakingSignal.LIKELY:
                signal_str = "[bold red]BREAKING[/bold red]"
            elif entry.breaking_signal == BreakingSignal.CLEAN:
                signal_str = "[green]CLEAN[/green]"
            else:
                signal_str = "[dim]UNKNOWN[/dim]"
            link = f"  [blue]{entry.changelog_url}[/blue]" if entry.changelog_url else ""
            con.print(
                f"  {signal_str}  [cyan]{entry.alias}[/cyan]"
                f"  {entry.pinned_version} → [bold]{entry.latest_version}[/bold]{link}"
            )

    # --- Module usage map ---
    if report.module_usage_map is not None:
        um = report.module_usage_map
        in_use = um.libraries_in_use()
        con.print()
        con.print(
            f"[bold]Module Usage Map[/bold] — "
            f"{um.modules_scanned} modules scanned, "
            f"{len(in_use)} libraries referenced"
        )
        for u in sorted(in_use, key=lambda x: -x.direct_count)[:5]:
            api_note = f"  [dim]({u.api_count} via api)[/dim]" if u.api_count else ""
            con.print(f"  [cyan]{u.alias}[/cyan] — {u.direct_count} direct{api_note}")
        if len(in_use) > 5:
            con.print(f"  [dim]…and {len(in_use) - 5} more (see report)[/dim]")

    # --- License audit ---
    if report.license_audit is not None:
        lic_audit = report.license_audit
        con.print()
        if not lic_audit.findings:
            con.print(
                f"[green]License Audit[/green] — "
                f"all {lic_audit.libraries_audited} libraries use permissive licenses"
            )
        else:
            violations = sum(
                1 for lf in lic_audit.findings if lf.tier == LicenseTier.STRONG_COPYLEFT
            )
            weak = sum(1 for lf in lic_audit.findings if lf.tier == LicenseTier.WEAK_COPYLEFT)
            unknown = sum(1 for lf in lic_audit.findings if lf.tier == LicenseTier.UNKNOWN)
            lic_parts: list[str] = []
            if violations:
                lic_parts.append(f"[bold red]{violations} strong copyleft[/bold red]")
            if weak:
                lic_parts.append(f"[bold yellow]{weak} weak copyleft[/bold yellow]")
            if unknown:
                lic_parts.append(f"[dim]{unknown} unknown[/dim]")
            con.print(
                f"[bold]License Audit[/bold] — {lic_audit.flagged_count} flagged"
                + (f": {', '.join(lic_parts)}" if lic_parts else "")
            )
            for lf in lic_audit.findings[:5]:
                if lf.tier == LicenseTier.STRONG_COPYLEFT:
                    tier_str = "[bold red]strong copyleft[/bold red]"
                elif lf.tier == LicenseTier.WEAK_COPYLEFT:
                    tier_str = "[bold yellow]weak copyleft[/bold yellow]"
                else:
                    tier_str = "[dim]unknown[/dim]"
                lic_name = lf.license_name or "not declared"
                con.print(f"  {tier_str}  [cyan]{lf.alias}[/cyan]  [dim]{lic_name}[/dim]")
            if lic_audit.flagged_count > 5:
                con.print(f"  [dim]…and {lic_audit.flagged_count - 5} more (see report)[/dim]")
            if lic_audit.permissive_count > 0:
                con.print(
                    f"  [dim]✅ {lic_audit.permissive_count} "
                    f"{'library' if lic_audit.permissive_count == 1 else 'libraries'} "
                    "permissive[/dim]"
                )

    # --- Risk score ---
    if report.risk_score_report is not None:
        _print_risk_score(report.risk_score_report, con)

    # --- Written files ---
    if written_files:
        con.print()
        out_dir = written_files[0].parent
        con.print(f"[bold]Reports written[/bold] → [blue]{out_dir}[/blue]")
        for path in written_files:
            con.print(f"  [dim]•[/dim] {path.name}")
        # Hint at the /analyze-freeze skill when both CSVs landed (RFC-0033).
        # The skill consumes freeze-inventory.csv + freeze-findings.csv; if
        # either is missing (e.g. CSV writers disabled) the hint is skipped.
        names = {p.name for p in written_files}
        if any(n.endswith("-inventory.csv") for n in names) and any(
            n.endswith("-findings.csv") for n in names
        ):
            con.print(
                f"  [dim]Tip: run [/dim][cyan]/analyze-freeze {out_dir}[/cyan]"
                "[dim] in Claude Code for insights.[/dim]"
            )


_RISK_LEVEL_STYLE: dict[RiskLevel, str] = {
    RiskLevel.CRITICAL: "bold red",
    RiskLevel.HIGH: "bold yellow",
    RiskLevel.MEDIUM: "yellow",
    RiskLevel.LOW: "blue",
    RiskLevel.NONE: "dim",
}


def _print_risk_score(rsr: RiskScoreReport, con: Console) -> None:
    con.print()
    top = rsr.top
    if not top:
        con.print(
            f"[green]Risk Score[/green] — "
            f"{rsr.libraries_scored} libraries scored, no risk signals detected"
        )
        return

    critical = rsr.critical_count
    high = rsr.high_count
    # RFC-0028: enumerate every populated severity bucket explicitly.
    # Pre-fix anything-non-critical-non-high collapsed to ``N other``,
    # which was actively misleading when MEDIUM/LOW dominated the
    # tail (stress test: console said "157 other" while MD showed
    # 137 medium + 20 low).
    medium = sum(1 for lib in rsr.scored_libraries if lib.level is RiskLevel.MEDIUM)
    low = sum(1 for lib in rsr.scored_libraries if lib.level is RiskLevel.LOW)
    rs_parts: list[str] = []
    if critical:
        rs_parts.append(f"[bold red]{critical} critical[/bold red]")
    if high:
        rs_parts.append(f"[bold yellow]{high} high[/bold yellow]")
    if medium:
        rs_parts.append(f"[yellow]{medium} medium[/yellow]")
    if low:
        rs_parts.append(f"[blue]{low} low[/blue]")
    con.print(
        f"[bold]Risk Score[/bold] (experimental) — "
        f"{len(rsr.scored_libraries)} libraries with non-zero score"
        + (f": {', '.join(rs_parts)}" if rs_parts else "")
        + f"  [dim]avg {rsr.avg_score:.1f} · max {rsr.max_score}[/dim]"
    )
    for lib in top[:5]:
        rs_style = _RISK_LEVEL_STYLE.get(lib.level, "")
        rs_label = lib.level.value.upper()
        con.print(
            f"  [{rs_style}]{lib.total_score:3d}[/{rs_style}]  "
            f"[{rs_style}]{rs_label}[/{rs_style}]  "
            f"[cyan]{lib.alias}[/cyan]  [dim]{lib.version}[/dim]"
        )
    if len(rsr.scored_libraries) > 5:
        con.print(f"  [dim]…and {len(rsr.scored_libraries) - 5} more (see report)[/dim]")


def print_diff_summary(
    diff: FreezeDiff,
    written_files: tuple[Path, ...],
    *,
    console: Console | None = None,
) -> None:
    """Print an executive summary of *diff* to the console using Rich.

    :param diff: The computed freeze diff.
    :param written_files: Paths of every file that was written.
    :param console: Optional Rich :class:`~rich.console.Console` instance.
    """
    con = console or Console()

    if diff.is_baseline:
        _print_baseline(diff, written_files, con)
    else:
        _print_diff(diff, written_files, con)


def _print_baseline(
    diff: FreezeDiff,
    written_files: tuple[Path, ...],
    con: Console,
) -> None:
    ts = diff.after_generated_at.isoformat(timespec="seconds")
    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="bold")
    grid.add_column()
    grid.add_row("Generated", ts)
    con.print(Panel(grid, title="[bold green]🌱 Baseline Established[/bold green]", expand=False))
    con.print()
    con.print("This is the first registered freeze report.")
    con.print("Future diff reports will compare against this baseline.")
    _print_written(written_files, con)


def _print_diff(
    diff: FreezeDiff,
    written_files: tuple[Path, ...],
    con: Console,
) -> None:
    before_ts = (
        diff.before_generated_at.isoformat(timespec="seconds") if diff.before_generated_at else "?"
    )
    after_ts = diff.after_generated_at.isoformat(timespec="seconds")

    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="bold")
    grid.add_column()
    grid.add_row("Before", before_ts)
    grid.add_row("After", after_ts)
    con.print(Panel(grid, title="[bold]Freeze Diff[/bold]", expand=False))

    # --- Libraries ---
    con.print()
    upgraded = len(diff.libraries_upgraded)
    added = len(diff.libraries_added)
    removed = len(diff.libraries_removed)
    downgraded = len(diff.libraries_downgraded)
    major = len(diff.libraries_major)
    minor = len(diff.libraries_minor)
    patch = len(diff.libraries_patch)

    if diff.library_changes:
        con.print(
            f"[bold]Libraries[/bold] — "
            f"[green]{upgraded} upgraded[/green] "
            f"({major} major, {minor} minor, {patch} patch)"
            + (f", [blue]{added} added[/blue]" if added else "")
            + (f", [red]{removed} removed[/red]" if removed else "")
            + (f", [bold red]{downgraded} downgraded[/bold red]" if downgraded else "")
        )
        # Highlight major upgrades
        if diff.libraries_major:
            for c in sorted(diff.libraries_major, key=lambda x: x.alias):
                con.print(
                    f"  [bold red]major[/bold red]  [cyan]{c.alias}[/cyan]"
                    f"  {c.before_version} → {c.after_version}"
                )
    else:
        con.print("[bold]Libraries[/bold] — no changes")

    # --- Plugins ---
    con.print()
    if diff.plugin_changes:
        con.print(f"[bold]Plugins[/bold] — {len(diff.plugin_changes)} changed")
    else:
        con.print("[bold]Plugins[/bold] — no changes")

    # --- Health findings ---
    con.print()
    introduced = len(diff.findings_introduced)
    resolved = len(diff.findings_resolved)
    if diff.finding_changes:
        parts = []
        if introduced:
            parts.append(f"[bold yellow]{introduced} introduced[/bold yellow]")
        if resolved:
            parts.append(f"[green]{resolved} resolved[/green]")
        con.print(f"[bold]Catalog Health[/bold] — {', '.join(parts)}")
    else:
        con.print("[bold]Catalog Health[/bold] — no changes")

    _print_written(written_files, con)


def _print_written(written_files: tuple[Path, ...], con: Console) -> None:
    if written_files:
        con.print()
        out_dir = written_files[0].parent
        con.print(f"[bold]Reports written[/bold] → [blue]{out_dir}[/blue]")
        for path in written_files:
            con.print(f"  [dim]•[/dim] {path.name}")
