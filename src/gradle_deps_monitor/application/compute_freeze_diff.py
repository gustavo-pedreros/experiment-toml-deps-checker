"""ComputeFreezeDiff — application use case for diffing two freeze snapshots."""

from __future__ import annotations

from gradle_deps_monitor.application.ports.snapshot_loader import (
    FindingSnapshot,
    FreezeSnapshot,
    LibrarySnapshot,
    PluginSnapshot,
)
from gradle_deps_monitor.domain.diff import (
    FindingChange,
    FreezeDiff,
    LibraryChange,
    PluginChange,
    classify_bump,
)


class ComputeFreezeDiff:
    """Compute a :class:`~gradle_deps_monitor.domain.diff.FreezeDiff` from two snapshots.

    Stateless — instantiate once and call :meth:`execute` for each pair.

    Usage::

        use_case = ComputeFreezeDiff()
        diff = use_case.execute(before_snapshot, after_snapshot)

    Pass ``before=None`` to produce a *baseline* diff (first-run scenario).
    """

    def execute(
        self,
        before: FreezeSnapshot | None,
        after: FreezeSnapshot,
    ) -> FreezeDiff:
        """Compare *before* and *after* and return a :class:`FreezeDiff`.

        :param before: The earlier snapshot, or ``None`` for a first-run baseline.
        :param after:  The later (current) snapshot.
        :returns: A :class:`FreezeDiff` describing all changes.
        """
        if before is None:
            return FreezeDiff(
                before_generated_at=None,
                after_generated_at=after.generated_at,
                library_changes=(),
                plugin_changes=(),
                finding_changes=(),
                is_baseline=True,
            )

        return FreezeDiff(
            before_generated_at=before.generated_at,
            after_generated_at=after.generated_at,
            library_changes=_diff_libraries(before.libraries, after.libraries),
            plugin_changes=_diff_plugins(before.plugins, after.plugins),
            finding_changes=_diff_findings(before.findings, after.findings),
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _diff_libraries(
    before: tuple[LibrarySnapshot, ...],
    after: tuple[LibrarySnapshot, ...],
) -> tuple[LibraryChange, ...]:
    before_map: dict[str, LibrarySnapshot] = {lib.coordinate: lib for lib in before}
    after_map: dict[str, LibrarySnapshot] = {lib.coordinate: lib for lib in after}

    all_coordinates = sorted(before_map.keys() | after_map.keys())
    changes: list[LibraryChange] = []

    for coord in all_coordinates:
        b = before_map.get(coord)
        a = after_map.get(coord)

        if b is None and a is not None:
            # Added
            changes.append(
                LibraryChange(
                    alias=a.alias,
                    coordinate=coord,
                    before_version=None,
                    after_version=a.version,
                    bump=None,
                )
            )
        elif b is not None and a is None:
            # Removed
            changes.append(
                LibraryChange(
                    alias=b.alias,
                    coordinate=coord,
                    before_version=b.version,
                    after_version=None,
                    bump=None,
                )
            )
        elif b is not None and a is not None and b.version != a.version:
            # Version changed
            changes.append(
                LibraryChange(
                    alias=a.alias,
                    coordinate=coord,
                    before_version=b.version,
                    after_version=a.version,
                    bump=classify_bump(b.version, a.version),
                )
            )
        # else: unchanged — omit from diff

    return tuple(changes)


def _diff_plugins(
    before: tuple[PluginSnapshot, ...],
    after: tuple[PluginSnapshot, ...],
) -> tuple[PluginChange, ...]:
    before_map: dict[str, PluginSnapshot] = {p.plugin_id: p for p in before}
    after_map: dict[str, PluginSnapshot] = {p.plugin_id: p for p in after}

    all_ids = sorted(before_map.keys() | after_map.keys())
    changes: list[PluginChange] = []

    for pid in all_ids:
        b = before_map.get(pid)
        a = after_map.get(pid)

        if b is None and a is not None:
            changes.append(
                PluginChange(
                    alias=a.alias,
                    plugin_id=pid,
                    before_version=None,
                    after_version=a.version,
                    bump=None,
                )
            )
        elif b is not None and a is None:
            changes.append(
                PluginChange(
                    alias=b.alias,
                    plugin_id=pid,
                    before_version=b.version,
                    after_version=None,
                    bump=None,
                )
            )
        elif b is not None and a is not None and b.version != a.version:
            changes.append(
                PluginChange(
                    alias=a.alias,
                    plugin_id=pid,
                    before_version=b.version,
                    after_version=a.version,
                    bump=classify_bump(b.version, a.version),
                )
            )

    return tuple(changes)


def _diff_findings(
    before: tuple[FindingSnapshot, ...],
    after: tuple[FindingSnapshot, ...],
) -> tuple[FindingChange, ...]:
    # Use (rule_id, severity, message) as the identity key.
    before_keys: set[tuple[str, str, str]] = {(f.rule_id, f.severity, f.message) for f in before}
    after_keys: set[tuple[str, str, str]] = {(f.rule_id, f.severity, f.message) for f in after}

    changes: list[FindingChange] = []

    for f in sorted(after, key=lambda x: (x.rule_id, x.message)):
        key = (f.rule_id, f.severity, f.message)
        if key not in before_keys:
            changes.append(
                FindingChange(
                    rule_id=f.rule_id,
                    severity=f.severity,
                    message=f.message,
                    status="introduced",
                )
            )

    for f in sorted(before, key=lambda x: (x.rule_id, x.message)):
        key = (f.rule_id, f.severity, f.message)
        if key not in after_keys:
            changes.append(
                FindingChange(
                    rule_id=f.rule_id,
                    severity=f.severity,
                    message=f.message,
                    status="resolved",
                )
            )

    return tuple(changes)
