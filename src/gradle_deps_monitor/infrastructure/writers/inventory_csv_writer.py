"""Inventory CSV writer — one row per catalog library (RFC-0017).

Tracer scope (PR #1 of 2): three columns — ``alias``, ``coordinate``,
``version`` — wired through the composition root so the file is
emitted on every ``check`` run. Subsequent enrichment (drift, risk
score, vulnerability count, license tier, BoM parent, duplicate
detection, etc.) lands in PR #2 of the RFC.

Uses Python's stdlib ``csv`` module with ``QUOTE_MINIMAL`` (Excel
default). UTF-8 without BOM — modern Excel and Google Sheets both
read UTF-8 cleanly; the BOM trips up Python consumers.
"""

from __future__ import annotations

import csv
from pathlib import Path

from gradle_deps_monitor.domain import FreezeReport

# Column order is part of the file's contract. Append new columns at
# the end in future revisions; never reorder or rename without a
# documented migration.
_COLUMNS: tuple[str, ...] = ("alias", "coordinate", "version")


class InventoryCsvWriter:
    """Serialises a :class:`~gradle_deps_monitor.domain.FreezeReport` to
    a library-centric CSV. RFC-0017."""

    def write(self, report: FreezeReport, dest: Path) -> None:
        """Write *report* to *dest*, creating parent directories as needed."""
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.writer(fh, quoting=csv.QUOTE_MINIMAL)
            writer.writerow(_COLUMNS)
            for lib in sorted(report.catalog.libraries, key=lambda lib: lib.alias):
                writer.writerow(
                    (
                        lib.alias,
                        lib.coordinate,
                        str(lib.version),
                    )
                )
