"""Markdown report writer."""

from __future__ import annotations

from pathlib import Path

from gradle_deps_monitor.domain import FreezeReport
from gradle_deps_monitor.domain.catalog import Bundle, Library, Plugin


class MarkdownWriter:
    """Serialises a :class:`~gradle_deps_monitor.domain.FreezeReport` to Markdown."""

    def write(self, report: FreezeReport, dest: Path) -> None:
        """Write *report* to *dest*, creating parent directories as needed."""
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(_render(report), encoding="utf-8")


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------


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
