"""TOML configuration loader (RFC-0012).

Reads ``gradle-deps-monitor.toml`` at the project root and produces an
:class:`~gradle_deps_monitor.domain.config.AppConfig`. The file is
optional: if it does not exist, all defaults apply.

Layer placement
---------------
This module lives in *infrastructure* because it performs I/O (reads
the filesystem, parses TOML). The output is a pure domain DTO so that
``application`` and ``presentation`` consumers never observe a file
path or a parsing error type leaking out.
"""

from __future__ import annotations

import logging
import tomllib
from pathlib import Path
from typing import Any

from gradle_deps_monitor.domain.config import AppConfig
from gradle_deps_monitor.domain.risk_score import RiskThresholds, RiskWeights

_LOGGER = logging.getLogger(__name__)

CONFIG_FILENAME = "gradle-deps-monitor.toml"

# Sections recognised by this loader. Unknown top-level sections produce
# a warning (so typos in user configs surface) but do not abort the run.
_KNOWN_SECTIONS = frozenset(
    {
        "risk_weights",
        "risk_thresholds",
        # Sections reserved for future RFCs are listed here so that early
        # adopters can populate them without triggering the unknown-section
        # warning. The values are not consumed yet.
        "cache",
        "output",
        "library_health",
    }
)


class ConfigError(ValueError):
    """Raised when ``gradle-deps-monitor.toml`` is present but invalid.

    The message always includes the absolute path of the offending file
    so the user can find it without re-reading the traceback.
    """


def load_config(project_root: Path) -> AppConfig:
    """Return an :class:`AppConfig` for *project_root*.

    *project_root* is the directory expected to contain
    ``gradle-deps-monitor.toml``. Typically this is the parent of the
    Gradle directory passed on the CLI (e.g. for ``check app/gradle``,
    *project_root* is ``app/``).

    :raises ConfigError: If a file is present but cannot be parsed or
        contains invalid section content.
    """
    config_path = project_root / CONFIG_FILENAME
    if not config_path.exists():
        return AppConfig()

    try:
        raw = config_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"Could not read {config_path}: {exc}") from exc

    try:
        data = tomllib.loads(raw)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"Invalid TOML in {config_path}: {exc}") from exc

    _warn_unknown_sections(data, config_path)

    weights = _parse_risk_weights(data.get("risk_weights"), config_path)
    thresholds = _parse_risk_thresholds(data.get("risk_thresholds"), config_path)

    return AppConfig(risk_weights=weights, risk_thresholds=thresholds)


# ---------------------------------------------------------------------------
# Section parsers
# ---------------------------------------------------------------------------


def _parse_risk_weights(section: Any, path: Path) -> RiskWeights:
    """Build a :class:`RiskWeights` from the optional ``[risk_weights]`` table."""
    if section is None:
        return RiskWeights()
    if not isinstance(section, dict):
        raise ConfigError(
            f"Section [risk_weights] in {path} must be a TOML table, got {type(section).__name__}."
        )

    defaults = RiskWeights()
    field_names = (
        "outdatedness",
        "cve",
        "abandonment",
        "blast_radius",
        "compliance",
        "license",
    )
    values: dict[str, int] = {}
    for name in field_names:
        if name in section:
            values[name] = _coerce_int(section[name], path, f"risk_weights.{name}")
        else:
            values[name] = getattr(defaults, name)

    unknown = set(section) - set(field_names)
    if unknown:
        _LOGGER.warning("Unknown keys in [risk_weights] in %s: %s (ignored)", path, sorted(unknown))

    try:
        return RiskWeights(**values)
    except ValueError as exc:
        raise ConfigError(f"Invalid [risk_weights] in {path}: {exc}") from exc


def _parse_risk_thresholds(section: Any, path: Path) -> RiskThresholds:
    """Build a :class:`RiskThresholds` from the optional ``[risk_thresholds]`` table."""
    if section is None:
        return RiskThresholds()
    if not isinstance(section, dict):
        raise ConfigError(
            f"Section [risk_thresholds] in {path} must be a TOML table, "
            f"got {type(section).__name__}."
        )

    defaults = RiskThresholds()
    field_names = ("critical", "high", "medium")
    values: dict[str, int] = {}
    for name in field_names:
        if name in section:
            values[name] = _coerce_int(section[name], path, f"risk_thresholds.{name}")
        else:
            values[name] = getattr(defaults, name)

    unknown = set(section) - set(field_names)
    if unknown:
        _LOGGER.warning(
            "Unknown keys in [risk_thresholds] in %s: %s (ignored)", path, sorted(unknown)
        )

    try:
        return RiskThresholds(**values)
    except ValueError as exc:
        raise ConfigError(f"Invalid [risk_thresholds] in {path}: {exc}") from exc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _coerce_int(value: Any, path: Path, key: str) -> int:
    """Reject TOML values that are not plain integers.

    TOML booleans are subclasses of ``int`` but here they are almost
    always a typo, so they are rejected explicitly.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(
            f"Value for {key} in {path} must be an integer, got {type(value).__name__} {value!r}."
        )
    return int(value)


def _warn_unknown_sections(data: dict[str, Any], path: Path) -> None:
    unknown = set(data) - _KNOWN_SECTIONS
    if unknown:
        _LOGGER.warning("Unknown sections in %s: %s (ignored)", path, sorted(unknown))
