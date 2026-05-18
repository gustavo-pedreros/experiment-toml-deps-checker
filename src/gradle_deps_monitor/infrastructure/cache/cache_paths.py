"""Cache-root resolution + bulk clear helpers (RFC-0029).

These functions own the three operational concerns the cache adapters
themselves don't:

- **Resolution order** for the cache root: ``GRADLE_DEPS_MONITOR_CACHE_ROOT``
  env var → :class:`~gradle_deps_monitor.domain.config.CacheConfig.root` →
  ``~/.cache/gradle-deps-monitor`` default.
- **Bulk purge** for ``--clear-cache`` (operator wipes the whole tree
  before a fresh run).
- **Ephemeral throwaway root** for ``--no-cache`` (this run never touches
  the persistent cache).
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from gradle_deps_monitor.domain.config import CacheConfig

CACHE_ROOT_ENV_VAR = "GRADLE_DEPS_MONITOR_CACHE_ROOT"
"""Environment variable name honoured by :func:`default_cache_root`."""

_DEFAULT_SUBDIR = ".cache/gradle-deps-monitor"


def default_cache_root() -> Path:
    """Return the cache root honouring ``GRADLE_DEPS_MONITOR_CACHE_ROOT``.

    Falls back to ``$HOME / .cache / gradle-deps-monitor`` when the env
    var is unset or empty. Does not create the directory; that is the
    cache adapters' responsibility on first write.
    """
    override = os.environ.get(CACHE_ROOT_ENV_VAR, "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / _DEFAULT_SUBDIR


def resolve_cache_root(cfg: CacheConfig) -> Path:
    """Apply the documented resolution order for the cache root.

    Order (highest priority first):

    1. ``GRADLE_DEPS_MONITOR_CACHE_ROOT`` environment variable.
    2. ``cfg.root`` from ``gradle-deps-monitor.toml`` ``[cache] root``.
    3. ``~/.cache/gradle-deps-monitor`` built-in default.
    """
    env_override = os.environ.get(CACHE_ROOT_ENV_VAR, "").strip()
    if env_override:
        return Path(env_override).expanduser()
    if cfg.root is not None:
        return cfg.root.expanduser()
    return default_cache_root()


def clear_cache(root: Path) -> None:
    """Recursively delete *root*.

    Silently succeeds when *root* does not exist (so ``--clear-cache``
    works on a first-run setup). Errors during deletion (permissions,
    busy file handles on Windows) are swallowed via
    ``ignore_errors=True`` — the next adapter write will recreate
    whatever is missing.
    """
    shutil.rmtree(root, ignore_errors=True)


def ephemeral_cache_root() -> Path:
    """Return a fresh temporary directory for ``--no-cache`` runs.

    The caller is responsible for cleanup (typically via
    :func:`atexit.register` wired in
    :mod:`gradle_deps_monitor.bootstrap`).
    """
    return Path(tempfile.mkdtemp(prefix="gradle-deps-monitor-nocache-"))
