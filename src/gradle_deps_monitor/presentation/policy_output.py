"""Render :class:`PolicyResult` to console + GitHub Actions annotations.

Two side-effects, both pure functions of the input:

* :func:`print_policy_section` writes a Rich-styled "Policy
  violations" / "Policy warnings" panel to the given console.
* :func:`emit_github_actions_annotations` writes one
  ``::error file=…::…`` or ``::warning file=…::…`` line per finding
  to stdout when running under GitHub Actions.

The CLI calls both after :class:`CheckCommand` returns, then maps
:attr:`PolicyResult.should_fail` to the process exit code.
"""

from __future__ import annotations

import os
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from gradle_deps_monitor.domain.policy import PolicyResult
from gradle_deps_monitor.domain.severity import CommonSeverity
from gradle_deps_monitor.domain.severity_style import style_for


def print_policy_section(
    result: PolicyResult,
    *,
    console: Console | None = None,
) -> None:
    """Render *result* as up to two Rich panels (violations + warnings).

    Emits nothing when the result has no rows in either bucket — the
    CLI calls this unconditionally and prefers a silent no-op over a
    "no policy hits" placeholder.
    """
    if not result.violations and not result.warnings:
        return

    con = console or Console()

    if result.violations:
        con.print(_panel(result.violations, title="Policy violations", error=True))
    if result.warnings:
        con.print(_panel(result.warnings, title="Policy warnings", error=False))


def emit_github_actions_annotations(
    result: PolicyResult,
    catalog_path: Path,
    *,
    env: dict[str, str] | None = None,
) -> None:
    """Print workflow annotations to stdout when running under GHA.

    GitHub Actions parses ``::error`` / ``::warning`` lines on a
    worker's stdout and surfaces them inline in the PR file diff.
    No-op when ``GITHUB_ACTIONS`` is not ``"true"`` so local runs
    stay quiet.
    """
    e = env if env is not None else os.environ
    if e.get("GITHUB_ACTIONS") != "true":
        return

    rel = _catalog_file_path(catalog_path)
    for v in result.violations:
        print(_annotation_line("error", rel, v.category, v.target, v.message))
    for w in result.warnings:
        print(_annotation_line("warning", rel, w.category, w.target, w.message))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _panel(
    rows: tuple,  # type: ignore[type-arg]
    *,
    title: str,
    error: bool,
) -> Panel:
    table = Table.grid(padding=(0, 1))
    table.add_column(justify="left")
    table.add_column(justify="left")
    table.add_column(justify="left")
    for v in rows:
        style = style_for(v.severity).rich_style
        icon = "✖" if v.severity == CommonSeverity.ERROR else "⚠"
        target = v.target or "—"
        table.add_row(
            f"[{style}]{icon} {v.category}[/]",
            f"[bold]{target}[/]",
            v.message,
        )
    border = "red" if error else "yellow"
    return Panel(table, title=title, border_style=border, expand=False)


def _annotation_line(
    level: str,
    file_rel: str,
    category: str,
    target: str | None,
    message: str,
) -> str:
    """Format one ``::level file=…::…`` line.

    Embedded ``\\r`` / ``\\n`` / ``::`` in *message* would break the
    GHA parser; escape per the workflow-commands spec.
    """
    safe = message.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A").replace(":", "%3A")
    target_str = f"{target} — " if target else ""
    return f"::{level} file={file_rel}::[{category}] {target_str}{safe}"


def _catalog_file_path(catalog_path: Path) -> str:
    """Resolve the catalog file path for GHA annotations.

    The CLI accepts a directory (the Gradle directory). The
    canonical file under it is ``libs.versions.toml``; if that
    doesn't exist (mostly in tests), fall back to the directory
    path itself.
    """
    candidate = catalog_path / "libs.versions.toml"
    target = candidate if candidate.exists() else catalog_path
    try:
        return str(target.relative_to(Path.cwd()))
    except ValueError:
        return str(target)
