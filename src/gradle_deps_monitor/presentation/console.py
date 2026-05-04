"""Console executive summaries rendered with Rich."""

from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from gradle_deps_monitor.domain import FreezeReport, Severity
from gradle_deps_monitor.domain.diff import FreezeDiff
from gradle_deps_monitor.domain.version import Stability

_SEVERITY_STYLE: dict[Severity, str] = {
    Severity.ERROR: "bold red",
    Severity.WARNING: "bold yellow",
    Severity.INFO: "blue",
    Severity.SUGGESTION: "dim",
}

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
            style = _SEVERITY_STYLE.get(finding.severity, "")
            label = _SEVERITY_LABEL.get(finding.severity, finding.severity.value)
            con.print(
                f"  [{style}]{label}[/{style}]  [dim]{finding.rule_id}[/dim]  {finding.message}"
            )
    else:
        con.print("[green]Catalog Health[/green] — no issues found")

    # --- Written files ---
    if written_files:
        con.print()
        out_dir = written_files[0].parent
        con.print(f"[bold]Reports written[/bold] → [blue]{out_dir}[/blue]")
        for path in written_files:
            con.print(f"  [dim]•[/dim] {path.name}")


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
