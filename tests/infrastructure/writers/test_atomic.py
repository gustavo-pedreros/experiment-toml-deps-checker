"""Tests for the atomic-write helper (RFC-0032).

Verifies the eight contract points the writers package relies on:
either *dest* contains the complete new content, or *dest* is left
untouched and no temp file survives. Covers both success and failure
paths, including ``KeyboardInterrupt`` mid-write.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from gradle_deps_monitor.infrastructure.writers._atomic import atomic_write


def _temp_siblings(dest: Path) -> list[Path]:
    """Return every sibling of *dest* whose name starts with ``.{dest.name}.``."""
    if not dest.parent.exists():
        return []
    prefix = f".{dest.name}."
    return [p for p in dest.parent.iterdir() if p.name.startswith(prefix)]


def test_writes_full_content_on_clean_exit(tmp_path: Path) -> None:
    dest = tmp_path / "out.txt"
    with atomic_write(dest) as fh:
        fh.write("hello\nworld\n")
    assert dest.read_text(encoding="utf-8") == "hello\nworld\n"


def test_creates_parent_directories(tmp_path: Path) -> None:
    dest = tmp_path / "nested" / "deep" / "out.txt"
    with atomic_write(dest) as fh:
        fh.write("ok")
    assert dest.is_file()
    assert dest.read_text(encoding="utf-8") == "ok"


def test_no_temp_file_after_clean_exit(tmp_path: Path) -> None:
    dest = tmp_path / "out.txt"
    with atomic_write(dest) as fh:
        fh.write("ok")
    assert _temp_siblings(dest) == []


def test_dest_unchanged_when_writer_raises(tmp_path: Path) -> None:
    dest = tmp_path / "out.txt"
    with pytest.raises(RuntimeError, match="boom"), atomic_write(dest) as fh:
        fh.write("partial")
        raise RuntimeError("boom")
    assert not dest.exists()


def test_temp_file_removed_when_writer_raises(tmp_path: Path) -> None:
    dest = tmp_path / "out.txt"
    with pytest.raises(RuntimeError), atomic_write(dest) as fh:
        fh.write("partial")
        raise RuntimeError("boom")
    assert _temp_siblings(dest) == []


def test_existing_dest_preserved_on_failure(tmp_path: Path) -> None:
    dest = tmp_path / "out.txt"
    dest.write_text("ORIGINAL", encoding="utf-8")
    with pytest.raises(RuntimeError), atomic_write(dest) as fh:
        fh.write("NEW CONTENT")
        raise RuntimeError("boom")
    assert dest.read_text(encoding="utf-8") == "ORIGINAL"
    assert _temp_siblings(dest) == []


def test_keyboard_interrupt_cleans_temp(tmp_path: Path) -> None:
    dest = tmp_path / "out.txt"
    with pytest.raises(KeyboardInterrupt), atomic_write(dest) as fh:
        fh.write("partial")
        raise KeyboardInterrupt
    assert not dest.exists()
    assert _temp_siblings(dest) == []


def test_newline_passthrough_for_csv(tmp_path: Path) -> None:
    """``newline=""`` is the option ``csv.writer`` requires; verify it
    reaches the underlying ``open`` so CSV rows aren't double-line-ended
    on Windows."""
    import csv

    dest = tmp_path / "out.csv"
    with atomic_write(dest, newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["a", "b"])
        writer.writerow(["1", "2"])
    # No CR padding — exactly one \n per row.
    raw = dest.read_bytes()
    assert raw == b"a,b\r\n1,2\r\n" or raw == b"a,b\n1,2\n"


def test_existing_dest_replaced_on_success(tmp_path: Path) -> None:
    """Happy-path replacement of an existing file."""
    dest = tmp_path / "out.txt"
    dest.write_text("ORIGINAL", encoding="utf-8")
    with atomic_write(dest) as fh:
        fh.write("NEW")
    assert dest.read_text(encoding="utf-8") == "NEW"


def test_temp_filename_pattern(tmp_path: Path) -> None:
    """Temp file should be a hidden sibling with PID+hex suffix so that
    a surviving leftover from a hard crash is easy to identify."""
    dest = tmp_path / "report.json"
    seen: list[str] = []

    with atomic_write(dest) as fh:
        # Inspect the live filesystem to find the temp file the helper opened.
        seen.extend(p.name for p in _temp_siblings(dest))
        fh.write("{}")

    assert len(seen) == 1, f"expected exactly one temp file, saw {seen}"
    name = seen[0]
    assert name.startswith(f".{dest.name}.")
    assert name.endswith(".tmp")
    # Sandwich between dest name and .tmp is "{pid}.{hex}".
    middle = name[len(f".{dest.name}.") : -len(".tmp")]
    pid_str, _, hex_str = middle.partition(".")
    assert pid_str == str(os.getpid())
    assert len(hex_str) == 8  # secrets.token_hex(4)
