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
        report = bootstrap.create_check_command().run(catalog_path, output_dir)
    except CatalogParseError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(f"Freeze report written to {output_dir}")
    typer.echo(f"  Libraries : {report.catalog.library_count}")
    typer.echo(f"  Plugins   : {report.catalog.plugin_count}")
    typer.echo(f"  Bundles   : {len(report.catalog.bundles)}")
