"""Console executive summary rendered with Rich (Step 10)."""

from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from gradle_deps_monitor.domain import FreezeReport, Severity
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
