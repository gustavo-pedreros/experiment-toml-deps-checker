"""Composition root.

Wires concrete infrastructure adapters into application use cases and
presentation command handlers. This is the only module permitted to import
from every layer; see ``docs/adr/0006-pragmatic-clean-architecture.md`` and
the import-linter contracts in ``pyproject.toml``.
"""

from __future__ import annotations

from gradle_deps_monitor.application.generate_freeze_report import GenerateFreezeReport
from gradle_deps_monitor.infrastructure.parsing.toml_catalog_parser import TomlCatalogParser
from gradle_deps_monitor.infrastructure.writers.json_writer import JsonWriter
from gradle_deps_monitor.infrastructure.writers.markdown_writer import MarkdownWriter
from gradle_deps_monitor.presentation.commands.check_command import CheckCommand

# Default stem for all report output files (e.g. "freeze.md", "freeze.json").
_REPORT_STEM = "freeze"


def create_check_command() -> CheckCommand:
    """Return a fully wired :class:`~...presentation.commands.check_command.CheckCommand`.

    Concrete adapters created here:

    - :class:`~...infrastructure.parsing.toml_catalog_parser.TomlCatalogParser`
    - :class:`~...infrastructure.writers.markdown_writer.MarkdownWriter`
    - :class:`~...infrastructure.writers.json_writer.JsonWriter`
    """
    parser = TomlCatalogParser()
    use_case = GenerateFreezeReport(catalog_parser=parser)
    return CheckCommand(
        use_case=use_case,
        writers=[
            (f"{_REPORT_STEM}.md", MarkdownWriter()),
            (f"{_REPORT_STEM}.json", JsonWriter()),
        ],
    )
