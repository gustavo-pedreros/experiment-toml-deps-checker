"""CheckCommand — presentation-layer handler for the 'check' CLI command."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from gradle_deps_monitor.application.generate_freeze_report import GenerateFreezeReport
from gradle_deps_monitor.application.ports.report_writer import ReportWriter
from gradle_deps_monitor.domain import FreezeReport


class CheckCommand:
    """Orchestrate the *check* sub-command: parse catalog → write reports.

    Depends only on application-layer abstractions; concrete infrastructure
    adapters are injected by the composition root in
    :mod:`gradle_deps_monitor.bootstrap`.

    :param use_case: The ``GenerateFreezeReport`` use case.
    :param writers: Sequence of ``(filename, writer)`` pairs — each writer
        receives the report and the resolved destination path
        ``output_dir / filename``.
    """

    def __init__(
        self,
        use_case: GenerateFreezeReport,
        writers: Sequence[tuple[str, ReportWriter]],
    ) -> None:
        self._use_case = use_case
        self._writers = list(writers)

    def run(self, catalog_path: Path, output_dir: Path) -> FreezeReport:
        """Execute the use case and write all reports to *output_dir*.

        :param catalog_path: Directory or file path forwarded to the parser.
        :param output_dir: Directory where output files are written (created
            if absent by the individual writers).
        :returns: The generated :class:`~gradle_deps_monitor.domain.FreezeReport`.
        :raises CatalogParseError: Propagated from the use case / parser.
        """
        report = self._use_case.execute(catalog_path)
        for filename, writer in self._writers:
            writer.write(report, output_dir / filename)
        return report
