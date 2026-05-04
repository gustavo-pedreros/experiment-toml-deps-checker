"""DiffCommand — presentation-layer handler for the 'diff' CLI command."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from gradle_deps_monitor.application.compute_freeze_diff import ComputeFreezeDiff
from gradle_deps_monitor.application.ports.diff_writer import DiffWriter
from gradle_deps_monitor.application.ports.snapshot_loader import SnapshotLoader
from gradle_deps_monitor.domain.diff import FreezeDiff


class DiffCommand:
    """Orchestrate the *diff* sub-command: load snapshots → compute diff → write reports.

    Depends only on application-layer abstractions; concrete infrastructure
    adapters are injected by the composition root in
    :mod:`gradle_deps_monitor.bootstrap`.

    :param use_case: The ``ComputeFreezeDiff`` use case.
    :param loader:   A :class:`~...application.ports.snapshot_loader.SnapshotLoader`
                     implementation used to load ``freeze.json`` files.
    :param writers:  Sequence of ``(filename, writer)`` pairs.
    """

    def __init__(
        self,
        use_case: ComputeFreezeDiff,
        loader: SnapshotLoader,
        writers: Sequence[tuple[str, DiffWriter]],
    ) -> None:
        self._use_case = use_case
        self._loader = loader
        self._writers = list(writers)

    def run(
        self,
        after_path: Path,
        before_path: Path | None,
        output_dir: Path,
    ) -> tuple[FreezeDiff, tuple[Path, ...]]:
        """Load snapshots, compute the diff, and write all output files.

        :param after_path:  Path to the newer ``freeze.json``.
        :param before_path: Path to the older ``freeze.json``, or ``None`` for
                            a first-run baseline (no comparison).
        :param output_dir:  Directory where output files are written.
        :returns: A ``(diff, written_files)`` tuple.
        :raises FileNotFoundError: If *after_path* or *before_path* (when provided) does not exist.
        :raises ValueError: If a snapshot file cannot be parsed or has an unsupported schema.
        """
        after = self._loader.load(after_path)
        before = self._loader.load(before_path) if before_path is not None else None

        diff = self._use_case.execute(before, after)

        written: list[Path] = []
        for filename, writer in self._writers:
            dest = output_dir / filename
            writer.write(diff, dest)
            written.append(dest)

        return diff, tuple(written)
