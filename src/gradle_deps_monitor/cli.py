"""Typer entry point for the gradle-deps-monitor CLI.

Wires Typer commands to use cases via the composition root in
:mod:`gradle_deps_monitor.bootstrap`. Command handler logic lives in
:mod:`gradle_deps_monitor.presentation.commands`.
"""

import os
from pathlib import Path
from typing import Annotated

import typer

from gradle_deps_monitor import __version__, bootstrap
from gradle_deps_monitor.application.evaluate_policy import PolicyEvaluator
from gradle_deps_monitor.application.ports.catalog_parser import CatalogParseError
from gradle_deps_monitor.domain.policy import Policy, WarningCategory
from gradle_deps_monitor.infrastructure.config.loader import ConfigError, load_config
from gradle_deps_monitor.presentation.console import print_diff_summary, print_summary
from gradle_deps_monitor.presentation.policy_output import (
    emit_github_actions_annotations,
    print_policy_section,
)

# Exit codes (RFC-0018 v1, ``sysexits.h`` style).
_EXIT_OK = 0
_EXIT_POLICY_VIOLATION = 1
_EXIT_USAGE = 2
_EXIT_CONFIG = 3


def _has_cve_credentials() -> bool:
    """Return True when at least one CVE advisory source has usable credentials."""
    if os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN"):
        return True
    return bool(os.environ.get("OSSINDEX_USER") and os.environ.get("OSSINDEX_API_KEY"))


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
    module_usage: Annotated[
        bool,
        typer.Option(
            "--module-usage",
            "-m",
            help=(
                "Scan build.gradle(.kts) files and add a module usage map to reports "
                "(opt-in; slower on large projects)."
            ),
        ),
    ] = False,
    risk_score: Annotated[
        bool,
        typer.Option(
            "--risk-score",
            "-r",
            help=(
                "Compute a 0-100 composite risk score per library and include a ranked "
                "breakdown in reports (opt-in; experimental — see ADR-0004)."
            ),
        ),
    ] = False,
    no_cache: Annotated[
        bool,
        typer.Option(
            "--no-cache",
            help=(
                "Bypass the persistent on-disk cache for this run. Adapters write to "
                "a tempdir cleaned up at exit; the persistent cache is left untouched. "
                "RFC-0029."
            ),
        ),
    ] = False,
    clear_cache: Annotated[
        bool,
        typer.Option(
            "--clear-cache",
            help=(
                "Purge the persistent cache before this run. Adapters rebuild the cache "
                "from fresh HTTP responses. No-op when combined with --no-cache."
            ),
        ),
    ] = False,
    cache_ttl: Annotated[
        int | None,
        typer.Option(
            "--cache-ttl",
            help=(
                "Override every adapter's cache TTL for this run (seconds). When unset, "
                "per-source defaults apply (Maven 3600s, advisory 86400s) and may be "
                "overridden via [cache] in gradle-deps-monitor.toml."
            ),
            min=0,
        ),
    ] = None,
    fail_on_errors: Annotated[
        bool,
        typer.Option(
            "--fail-on-errors",
            help=(
                "Exit with code 1 when any error-level finding is present "
                "(critical CVE, compliance violation, toolchain error, "
                "strong-copyleft license). RFC-0018."
            ),
        ),
    ] = False,
    warn_on: Annotated[
        str | None,
        typer.Option(
            "--warn-on",
            help=(
                "Comma-separated warning categories to surface in a 'Policy "
                "warnings' section (does not change exit code). Valid: "
                "high-vulnerability, compliance, toolchain, library-health, "
                "deprecated, breaking, license. RFC-0018."
            ),
        ),
    ] = None,
    slack: Annotated[
        bool | None,
        typer.Option(
            "--slack/--no-slack",
            help=(
                "Whether to write freeze-slack.json (Slack Block Kit). "
                "Opt-in since RFC-0034. When unset, defers to "
                "[output] slack in gradle-deps-monitor.toml (default false). "
                "Flag wins over config when both are present."
            ),
        ),
    ] = None,
) -> None:
    """Generate a freeze report for the given Gradle catalog directory."""
    if risk_score and not _has_cve_credentials():
        typer.echo(
            "Warning: --risk-score is enabled but no CVE advisory credentials "
            "are set. The CVE dimension will score 0 for every library. Set "
            "GITHUB_TOKEN (or GH_TOKEN) and/or OSSINDEX_USER + OSSINDEX_API_KEY "
            "to populate it.",
            err=True,
        )

    warn_categories = _parse_warn_on(warn_on)

    try:
        # The Gradle directory's parent is the project root by convention
        # (e.g. ``app/gradle`` → project root ``app``). RFC-0012.
        app_config = load_config(catalog_path.parent)
    except ConfigError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=_EXIT_CONFIG) from exc

    try:
        report, written_files = bootstrap.create_check_command(
            module_usage=module_usage,
            risk_score=risk_score,
            app_config=app_config,
            no_cache=no_cache,
            clear_cache_first=clear_cache,
            cache_ttl_override=cache_ttl,
            slack=slack,
        ).run(catalog_path, output_dir)
    except CatalogParseError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=_EXIT_CONFIG) from exc

    print_summary(report, written_files)

    if fail_on_errors or warn_categories:
        policy = Policy(
            fail_on_errors=fail_on_errors,
            warn_on=frozenset(warn_categories),
        )
        result = PolicyEvaluator().evaluate(report, policy)
        print_policy_section(result)
        emit_github_actions_annotations(result, catalog_path)
        if result.should_fail:
            raise typer.Exit(code=_EXIT_POLICY_VIOLATION)


def _parse_warn_on(value: str | None) -> tuple[WarningCategory, ...]:
    """Parse ``--warn-on a,b,c`` into a tuple of :class:`WarningCategory`.

    Unknown categories raise :class:`typer.BadParameter`, which Typer
    converts to exit code ``2`` (usage error per RFC-0018 v1).
    """
    if not value:
        return ()
    raw = [piece.strip() for piece in value.split(",") if piece.strip()]
    out: list[WarningCategory] = []
    valid = {c.value for c in WarningCategory}
    for piece in raw:
        if piece not in valid:
            raise typer.BadParameter(
                f"Unknown warning category {piece!r}. Valid: {', '.join(sorted(valid))}.",
                param_hint="--warn-on",
            )
        out.append(WarningCategory(piece))
    return tuple(out)


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
    slack: Annotated[
        bool | None,
        typer.Option(
            "--slack/--no-slack",
            help=(
                "Whether to write freeze-diff-slack.json (Slack Block Kit). "
                "Opt-in since RFC-0034. When unset, defers to "
                "[output] slack in gradle-deps-monitor.toml at cwd "
                "(default false). Flag wins over config when both are present."
            ),
        ),
    ] = None,
) -> None:
    """Diff two freeze reports and write a comparative summary.

    Pass only AFTER to establish a baseline (first-run scenario).
    Pass --prev BEFORE to compare two existing reports.
    """
    try:
        # Diff is not project-rooted (no gradle dir argument); we look
        # for gradle-deps-monitor.toml in cwd as a best-effort source
        # of the [output] section. Missing file is fine — defaults apply.
        app_config = load_config(Path.cwd())
    except ConfigError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=_EXIT_CONFIG) from exc

    try:
        freeze_diff, written_files = bootstrap.create_diff_command(
            app_config=app_config,
            slack=slack,
        ).run(after, prev, output_dir)
    except (FileNotFoundError, ValueError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    print_diff_summary(freeze_diff, written_files)
