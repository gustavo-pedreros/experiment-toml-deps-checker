"""DiffWriter port — output adapter interface for FreezeDiff reports."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from gradle_deps_monitor.domain.diff import FreezeDiff


class DiffWriter(Protocol):
    """Write a :class:`~gradle_deps_monitor.domain.diff.FreezeDiff` to persistent storage."""

    def write(self, diff: FreezeDiff, dest: Path) -> None:
        """Serialise *diff* and write it to *dest*.

        :param diff: The computed diff to write.
        :param dest: Destination file path (parent directories are created as needed).
        """
        ...
