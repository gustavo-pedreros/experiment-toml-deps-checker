"""Typer entry point for the gradle-deps-monitor CLI.

Wires Typer commands to use cases via the composition root in
:mod:`gradle_deps_monitor.bootstrap`. Phase 1 work in progress: command
handlers will be moved to :mod:`gradle_deps_monitor.presentation.commands`
once their use cases are implemented.
"""

from pathlib import Path
from typing import Annotated

import typer

from gradle_deps_monitor import __version__

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
) -> None:
    """Generate a freeze report for the given Gradle catalog directory.

    Phase 1 work in progress: this command is not yet wired to the analysis
    pipeline. Future steps will add TOML parsing, version registry queries,
    and report generation.
    """
    typer.echo(f"check: not yet implemented (received: {catalog_path})")
