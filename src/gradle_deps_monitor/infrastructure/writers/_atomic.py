"""Atomic file-write helper for the writers package (RFC-0032).

All eight report writers go through :func:`atomic_write` so that a
process killed mid-write (SIGTERM, OOM, Ctrl-C) never leaves a
half-rendered file on disk. Either the new content is fully written
and renamed into place, or the previous file (if any) is left
untouched.

The helper deliberately uses a **sibling temp file** rather than
``tempfile.mkdtemp()``: :func:`os.replace` is only atomic across the
same filesystem, and same-directory guarantees that.
"""

from __future__ import annotations

import os
import secrets
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TextIO


@contextmanager
def atomic_write(
    dest: Path,
    *,
    encoding: str = "utf-8",
    newline: str | None = None,
) -> Iterator[TextIO]:
    """Open *dest* for atomic text-mode writing.

    Yields a text file handle pointing at a sibling temp file. On
    clean exit the temp file is renamed to *dest* via
    :func:`os.replace`. On any exception (including
    :class:`KeyboardInterrupt` and :class:`SystemExit`) the temp file
    is removed and *dest* is left untouched.

    Parent directories are created with ``mkdir(parents=True,
    exist_ok=True)`` before opening so callers don't need to repeat
    that boilerplate.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(f".{dest.name}.{os.getpid()}.{secrets.token_hex(4)}.tmp")
    fh = tmp.open("w", encoding=encoding, newline=newline)
    try:
        yield fh
    except BaseException:
        fh.close()
        tmp.unlink(missing_ok=True)
        raise
    else:
        fh.close()
        os.replace(tmp, dest)
