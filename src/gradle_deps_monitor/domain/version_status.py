"""Version-status domain model (RFC-0013).

A first-class per-library record of where the pinned version sits
relative to the latest stable on Maven Central / Google Maven.
Consumed by:

- the markdown / JSON / Slack writers (per-library drift column,
  outdated counts)
- the risk score's outdatedness dimension (replaces the
  changelog-only signal that only fired on major upgrades)

The drift classifier intentionally stays simple: full Maven
version-ordering semantics (qualifiers, ranges) are out of scope.
The classifier compares the leading numeric components of the two
strings and ignores qualifiers, which is sufficient for the freeze
audience (Android catalogs typically pin clean ``X.Y.Z`` releases).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from gradle_deps_monitor.domain.version import MavenVersion


class VersionDrift(StrEnum):
    """How far the pinned version is from the latest stable.

    Ordering, smallest to largest:

    .. code-block:: text

        NONE  <  PATCH  <  MINOR  <  MAJOR  <  UNKNOWN

    ``UNKNOWN`` is reserved for libraries whose latest version
    could not be resolved (network failure, unlisted artefact, or
    a pinned version string that does not parse).
    """

    NONE = "none"  # pinned == latest
    PATCH = "patch"  # 1.2.3 → 1.2.4
    MINOR = "minor"  # 1.2.3 → 1.3.0
    MAJOR = "major"  # 1.2.3 → 2.0.0
    UNKNOWN = "unknown"  # latest not resolvable, or unparseable pinned


@dataclass(frozen=True)
class LibraryVersionStatus:
    """Where one catalog library sits relative to the latest stable release.

    Attributes:
        alias:      Catalog alias (the key in ``[libraries]``).
        coordinate: ``"group:artifact"`` Maven coordinate.
        pinned:     Version declared in ``libs.versions.toml``.
        latest:     Latest stable release. ``None`` when no
                    registry returned a value (artifact unlisted or
                    network errors silently swallowed by the
                    resolver).
        drift:      Bucket classification of ``pinned`` vs
                    ``latest``. See :class:`VersionDrift`.
    """

    alias: str
    coordinate: str
    pinned: MavenVersion
    latest: MavenVersion | None
    drift: VersionDrift


# ---------------------------------------------------------------------------
# Drift computation
# ---------------------------------------------------------------------------


def compute_drift(pinned: MavenVersion, latest: MavenVersion | None) -> VersionDrift:
    """Bucket the gap between *pinned* and *latest*.

    Returns :attr:`VersionDrift.UNKNOWN` when *latest* is ``None`` or
    when either version's leading numeric component cannot be parsed.
    """
    if latest is None:
        return VersionDrift.UNKNOWN

    pinned_parts = _numeric_components(pinned.raw)
    latest_parts = _numeric_components(latest.raw)
    if pinned_parts is None or latest_parts is None:
        return VersionDrift.UNKNOWN

    # Normalise length to three components (X.Y.Z), padding with 0.
    pinned_xyz = (*pinned_parts, 0, 0, 0)[:3]
    latest_xyz = (*latest_parts, 0, 0, 0)[:3]

    if latest_xyz <= pinned_xyz:
        return VersionDrift.NONE
    if latest_xyz[0] > pinned_xyz[0]:
        return VersionDrift.MAJOR
    if latest_xyz[1] > pinned_xyz[1]:
        return VersionDrift.MINOR
    return VersionDrift.PATCH


def major_delta(pinned: MavenVersion, latest: MavenVersion | None) -> int:
    """Return the number of full major versions *pinned* is behind *latest*.

    Returns 0 when *latest* is ``None``, when neither version parses, or
    when *pinned* is at least as new as *latest*.
    """
    if latest is None:
        return 0
    p = _numeric_components(pinned.raw)
    l = _numeric_components(latest.raw)  # noqa: E741 (single-letter latch by convention)
    if p is None or l is None:
        return 0
    return max(0, l[0] - p[0])


def _numeric_components(raw: str) -> tuple[int, ...] | None:
    """Extract the leading dotted numeric prefix of *raw*.

    Stops at the first non-numeric component. Returns ``None`` when no
    numeric prefix exists (e.g. ``"alpha"`` or empty string).
    """
    components: list[int] = []
    for part in raw.split("."):
        digits: list[str] = []
        for ch in part:
            if ch.isdigit():
                digits.append(ch)
            else:
                break
        if not digits:
            break
        components.append(int("".join(digits)))
    if not components:
        return None
    return tuple(components)
