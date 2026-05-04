"""FreezeDiff — domain objects for comparing two freeze snapshots.

A :class:`FreezeDiff` captures what changed between two consecutive freeze
reports: libraries / plugins added, removed, or version-bumped, and health
findings that appeared or were resolved.

All objects are immutable value objects (frozen dataclasses).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Literal

# ---------------------------------------------------------------------------
# Version bump classification
# ---------------------------------------------------------------------------

_LEADING_NUMS = re.compile(r"^(\d+)(?:\.(\d+))?(?:\.(\d+))?")


def _numeric_parts(version: str) -> tuple[int, int, int]:
    """Extract the leading ``(major, minor, patch)`` integers from *version*."""
    m = _LEADING_NUMS.match(version)
    if not m:
        return (0, 0, 0)
    return (
        int(m.group(1) or 0),
        int(m.group(2) or 0),
        int(m.group(3) or 0),
    )


class VersionBump(StrEnum):
    """Coarse classification of a version change between two snapshots."""

    MAJOR = "major"
    MINOR = "minor"
    PATCH = "patch"
    #: Pre-release progression within the same numeric prefix
    #: (e.g. ``1.0.0-alpha01`` → ``1.0.0-alpha02`` or ``1.0.0-alpha01`` → ``1.0.0``).
    PRE_RELEASE = "pre-release"
    DOWNGRADE = "downgrade"


def classify_bump(before: str, after: str) -> VersionBump:
    """Classify the version change from *before* to *after*.

    Uses the leading numeric triple ``(major, minor, patch)`` for comparison,
    ignoring pre-release suffixes for ordering purposes.

    :param before: Version string of the earlier snapshot.
    :param after:  Version string of the later snapshot.
    :returns: A :class:`VersionBump` value.
    """
    b = _numeric_parts(before)
    a = _numeric_parts(after)
    if a == b:
        # Same numeric prefix — only pre-release channel changed.
        return VersionBump.PRE_RELEASE
    if a > b:
        if a[0] > b[0]:
            return VersionBump.MAJOR
        if a[1] > b[1]:
            return VersionBump.MINOR
        return VersionBump.PATCH
    return VersionBump.DOWNGRADE


# ---------------------------------------------------------------------------
# Change records
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LibraryChange:
    """A single library that was added, removed, or version-changed.

    :param alias:          Catalog alias (e.g. ``core-ktx``).
    :param coordinate:     Maven coordinate ``group:artifact``.
    :param before_version: Version in the earlier snapshot, or ``None`` if the
                           library was added.
    :param after_version:  Version in the later snapshot, or ``None`` if the
                           library was removed.
    :param bump:           How the version changed; ``None`` for add/remove.
    """

    alias: str
    coordinate: str
    before_version: str | None
    after_version: str | None
    bump: VersionBump | None

    @property
    def kind(self) -> Literal["added", "removed", "upgraded", "downgraded", "pre-release"]:
        if self.before_version is None:
            return "added"
        if self.after_version is None:
            return "removed"
        if self.bump is VersionBump.DOWNGRADE:
            return "downgraded"
        if self.bump is VersionBump.PRE_RELEASE:
            return "pre-release"
        return "upgraded"


@dataclass(frozen=True)
class PluginChange:
    """A single plugin that was added, removed, or version-changed.

    :param alias:          Catalog alias (e.g. ``kotlin-android``).
    :param plugin_id:      Gradle plugin id (e.g. ``org.jetbrains.kotlin.android``).
    :param before_version: Version in the earlier snapshot, or ``None`` if added.
    :param after_version:  Version in the later snapshot, or ``None`` if removed.
    :param bump:           How the version changed; ``None`` for add/remove.
    """

    alias: str
    plugin_id: str
    before_version: str | None
    after_version: str | None
    bump: VersionBump | None

    @property
    def kind(self) -> Literal["added", "removed", "upgraded", "downgraded", "pre-release"]:
        if self.before_version is None:
            return "added"
        if self.after_version is None:
            return "removed"
        if self.bump is VersionBump.DOWNGRADE:
            return "downgraded"
        if self.bump is VersionBump.PRE_RELEASE:
            return "pre-release"
        return "upgraded"


@dataclass(frozen=True)
class FindingChange:
    """A health finding that appeared or was resolved between two snapshots.

    :param rule_id:  The rule that produced this finding (e.g. ``HDX-001``).
    :param severity: Severity string (``error``, ``warning``, ``info``, ``suggestion``).
    :param message:  Human-readable description of the finding.
    :param status:   ``"introduced"`` if new in the later snapshot; ``"resolved"``
                     if present in the earlier snapshot but absent in the later one.
    """

    rule_id: str
    severity: str
    message: str
    status: Literal["introduced", "resolved"]


# ---------------------------------------------------------------------------
# Aggregate diff object
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FreezeDiff:
    """Comparison between two consecutive freeze snapshots.

    :param before_generated_at: Timestamp of the earlier snapshot.
    :param after_generated_at:  Timestamp of the later snapshot.
    :param library_changes:     Changed libraries (add/remove/version-bump only;
                                unchanged libraries are omitted).
    :param plugin_changes:      Changed plugins.
    :param finding_changes:     Findings that appeared or were resolved.
    :param is_baseline:         ``True`` when there is no earlier snapshot and this
                                report represents the first registered freeze.
    """

    before_generated_at: datetime | None
    after_generated_at: datetime
    library_changes: tuple[LibraryChange, ...]
    plugin_changes: tuple[PluginChange, ...]
    finding_changes: tuple[FindingChange, ...]
    is_baseline: bool = False

    # ------------------------------------------------------------------
    # Library convenience views
    # ------------------------------------------------------------------

    @property
    def libraries_added(self) -> tuple[LibraryChange, ...]:
        return tuple(c for c in self.library_changes if c.before_version is None)

    @property
    def libraries_removed(self) -> tuple[LibraryChange, ...]:
        return tuple(c for c in self.library_changes if c.after_version is None)

    @property
    def libraries_upgraded(self) -> tuple[LibraryChange, ...]:
        """All version upgrades (major + minor + patch + pre-release)."""
        return tuple(
            c
            for c in self.library_changes
            if c.bump is not None and c.bump is not VersionBump.DOWNGRADE
        )

    @property
    def libraries_downgraded(self) -> tuple[LibraryChange, ...]:
        return tuple(c for c in self.library_changes if c.bump is VersionBump.DOWNGRADE)

    @property
    def libraries_major(self) -> tuple[LibraryChange, ...]:
        return tuple(c for c in self.library_changes if c.bump is VersionBump.MAJOR)

    @property
    def libraries_minor(self) -> tuple[LibraryChange, ...]:
        return tuple(c for c in self.library_changes if c.bump is VersionBump.MINOR)

    @property
    def libraries_patch(self) -> tuple[LibraryChange, ...]:
        return tuple(c for c in self.library_changes if c.bump is VersionBump.PATCH)

    # ------------------------------------------------------------------
    # Plugin convenience views
    # ------------------------------------------------------------------

    @property
    def plugins_added(self) -> tuple[PluginChange, ...]:
        return tuple(c for c in self.plugin_changes if c.before_version is None)

    @property
    def plugins_removed(self) -> tuple[PluginChange, ...]:
        return tuple(c for c in self.plugin_changes if c.after_version is None)

    @property
    def plugins_upgraded(self) -> tuple[PluginChange, ...]:
        return tuple(
            c
            for c in self.plugin_changes
            if c.bump is not None and c.bump is not VersionBump.DOWNGRADE
        )

    @property
    def plugins_downgraded(self) -> tuple[PluginChange, ...]:
        return tuple(c for c in self.plugin_changes if c.bump is VersionBump.DOWNGRADE)

    # ------------------------------------------------------------------
    # Finding convenience views
    # ------------------------------------------------------------------

    @property
    def findings_introduced(self) -> tuple[FindingChange, ...]:
        return tuple(f for f in self.finding_changes if f.status == "introduced")

    @property
    def findings_resolved(self) -> tuple[FindingChange, ...]:
        return tuple(f for f in self.finding_changes if f.status == "resolved")

    # ------------------------------------------------------------------
    # General
    # ------------------------------------------------------------------

    @property
    def has_changes(self) -> bool:
        """``True`` if any library, plugin, or finding changed."""
        return bool(self.library_changes or self.plugin_changes or self.finding_changes)
