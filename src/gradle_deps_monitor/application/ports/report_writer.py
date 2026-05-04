"""ReportWriter port — outbound protocol for serialising a FreezeReport."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from gradle_deps_monitor.domain import FreezeReport


class ReportWriter(Protocol):
    """Outbound port: serialise a :class:`~gradle_deps_monitor.domain.FreezeReport` to disk."""

    def write(self, report: FreezeReport, dest: Path) -> None:
        """Write *report* to the file at *dest*.

        The writer creates any missing parent directories.

        :param report: The report to serialise.
        :param dest: Absolute path to the output file (caller controls the name).
        """
        ...
