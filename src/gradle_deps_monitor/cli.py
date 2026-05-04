"""Typer entry point for the gradle-deps-monitor CLI.

Wires Typer commands to use cases via the composition root in
:mod:`gradle_deps_monitor.bootstrap`. Command handler logic lives in
:mod:`gradle_deps_monitor.presentation.commands`.
"""

from pathlib import Path
from typing import Annotated

import typer

from gradle_deps_monitor import __version__, bootstrap
from gradle_deps_monitor.application.ports.catalog_parser import CatalogParseError
from gradle_deps_monitor.presentation.console import print_diff_summary, print_summary

app = typer.Typer(
    name="gradle-deps-monitor",
    help="Freeze-time technical due-diligence report for Android / Gradle projects.",
    add_completion=False,
    no_args_is_help=True,
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"gradle-deps-monitor {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    _version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=_version_callback,
            is_eager=True,
            help="Show the version and exit.",
        ),
    ] = False,
) -> None:
    """Top-level CLI entry point."""


@app.command()
def check(
    catalog_path: Annotated[
        Path,
        typer.Argument(
            help="Path to the Gradle directory containing libs.versions.toml.",
            exists=True,
            file_okay=False,
            dir_okay=True,
            readable=True,
            resolve_path=True,
        ),
    ],
    output_dir: Annotated[
        Path,
        typer.Option(
            "--out",
            "-o",
            help="Directory where reports are written (created if absent).",
        ),
    ] = Path("reports"),
) -> None:
    """Generate a freeze report for the given Gradle catalog directory."""
    try:
        report, written_files = bootstrap.create_check_command().run(catalog_path, output_dir)
    except CatalogParseError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    print_summary(report, written_files)


@app.command()
def diff(
    after: Annotated[
        Path,
        typer.Argument(
            help="Path to the newer freeze.json report.",
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
            resolve_path=True,
        ),
    ],
    prev: Annotated[
        Path | None,
        typer.Option(
            "--prev",
            "-p",
            help="Path to the older freeze.json report. Omit to establish a baseline.",
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
            resolve_path=True,
        ),
    ] = None,
    output_dir: Annotated[
        Path,
        typer.Option(
            "--out",
            "-o",
            help="Directory where diff reports are written (created if absent).",
        ),
    ] = Path("reports"),
) -> None:
    """Diff two freeze reports and write a comparative summary.

    Pass only AFTER to establish a baseline (first-run scenario).
    Pass --prev BEFORE to compare two existing reports.
    """
    try:
        freeze_diff, written_files = bootstrap.create_diff_command().run(after, prev, output_dir)
    except (FileNotFoundError, ValueError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    print_diff_summary(freeze_diff, written_files)
