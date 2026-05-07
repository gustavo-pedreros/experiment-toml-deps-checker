"""DiffSlackWriter — serialises a FreezeDiff to Slack Block Kit JSON."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from gradle_deps_monitor.domain.diff import FreezeDiff, VersionBump
from gradle_deps_monitor.domain.finding import Severity
from gradle_deps_monitor.domain.severity_style import style_for

_MAX_ENTRIES = 8  # Max library rows shown per section in Slack


def _severity_emoji(severity_value: str) -> str:
    """Resolve a serialised severity string to its unified Slack emoji.

    The diff loader stores severity as a plain string for forward-compat;
    mapping it back through :class:`Severity` keeps the diff writer aligned
    with the freeze writer (RFC-0016b).
    """
    try:
        return style_for(Severity(severity_value).to_common()).slack_emoji
    except ValueError:
        return ""


class DiffSlackWriter:
    """Writes a :class:`~gradle_deps_monitor.domain.diff.FreezeDiff` as Slack Block Kit JSON."""

    def write(self, diff: FreezeDiff, dest: Path) -> None:
        """Write *diff* to *dest*, creating parent directories as needed."""
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(
            json.dumps(_build_payload(diff), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )


# ---------------------------------------------------------------------------
# Block Kit helpers
# ---------------------------------------------------------------------------


def _build_payload(diff: FreezeDiff) -> dict[str, Any]:
    if diff.is_baseline:
        return {"blocks": _baseline_blocks(diff)}
    return {"blocks": _diff_blocks(diff)}


def _baseline_blocks(diff: FreezeDiff) -> list[dict[str, Any]]:
    ts = diff.after_generated_at.isoformat(timespec="seconds")
    return [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": ":seedling: Gradle Freeze — Baseline Established",
                "emoji": True,
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*Generated:* {ts}\n"
                    "This is the first registered freeze report. "
                    "Future diff reports will compare against this baseline."
                ),
            },
        },
    ]


def _diff_blocks(diff: FreezeDiff) -> list[dict[str, Any]]:
    before_date = diff.before_generated_at.strftime("%Y-%m-%d") if diff.before_generated_at else "?"
    after_date = diff.after_generated_at.strftime("%Y-%m-%d")

    blocks: list[dict[str, Any]] = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f":bar_chart: Freeze Diff: {before_date} → {after_date}",
                "emoji": True,
            },
        },
        _summary_block(diff),
        {"type": "divider"},
    ]

    lib_block = _libraries_block(diff)
    if lib_block:
        blocks.append(lib_block)
        blocks.append({"type": "divider"})

    plugin_block = _plugins_block(diff)
    if plugin_block:
        blocks.append(plugin_block)
        blocks.append({"type": "divider"})

    blocks.append(_findings_block(diff))

    return blocks


def _summary_block(diff: FreezeDiff) -> dict[str, Any]:
    lib_upgraded = len(diff.libraries_upgraded)
    lib_added = len(diff.libraries_added)
    lib_removed = len(diff.libraries_removed)
    lib_major = len(diff.libraries_major)

    lib_text = f"*Libraries changed:* {len(diff.library_changes)}"
    if lib_upgraded:
        lib_text += f"\n  ↑ {lib_upgraded} upgraded"
        if lib_major:
            lib_text += f" ({lib_major} :warning: major)"
    if lib_added:
        lib_text += f"\n  + {lib_added} added"
    if lib_removed:
        lib_text += f"\n  - {lib_removed} removed"

    plugin_text = f"*Plugins changed:* {len(diff.plugin_changes)}"
    if diff.plugin_changes:
        added = len(diff.plugins_added)
        removed = len(diff.plugins_removed)
        upgraded = len(diff.plugins_upgraded)
        if upgraded:
            plugin_text += f"\n  ↑ {upgraded} upgraded"
        if added:
            plugin_text += f"\n  + {added} added"
        if removed:
            plugin_text += f"\n  - {removed} removed"

    return {
        "type": "section",
        "fields": [
            {"type": "mrkdwn", "text": lib_text},
            {"type": "mrkdwn", "text": plugin_text},
        ],
    }


def _libraries_block(diff: FreezeDiff) -> dict[str, Any] | None:
    if not diff.library_changes:
        return None

    lines: list[str] = ["*:books: Libraries*"]

    # Upgraded — show major first, then a combined list
    major = list(diff.libraries_major)
    if major:
        lines.append(f"\n:warning: *Major upgrades ({len(major)}):*")
        for c in major[:_MAX_ENTRIES]:
            lines.append(f"• `{c.alias}` {c.before_version} → {c.after_version}")
        if len(major) > _MAX_ENTRIES:
            lines.append(f"_…and {len(major) - _MAX_ENTRIES} more_")

    other_upgraded = [c for c in diff.libraries_upgraded if c.bump is not VersionBump.MAJOR]
    if other_upgraded:
        minor_count = len(diff.libraries_minor)
        patch_count = len(diff.libraries_patch)
        pre_count = len([c for c in diff.library_changes if c.bump is VersionBump.PRE_RELEASE])
        parts = []
        if minor_count:
            parts.append(f"{minor_count} minor")
        if patch_count:
            parts.append(f"{patch_count} patch")
        if pre_count:
            parts.append(f"{pre_count} pre-release")
        lines.append(f"\n↑ *Other upgrades:* {', '.join(parts)}")

    if diff.libraries_added:
        lines.append(f"\n+ *Added ({len(diff.libraries_added)}):*")
        for c in sorted(diff.libraries_added, key=lambda x: x.alias)[:_MAX_ENTRIES]:
            lines.append(f"• `{c.alias}` — {c.after_version}")
        if len(diff.libraries_added) > _MAX_ENTRIES:
            lines.append(f"_…and {len(diff.libraries_added) - _MAX_ENTRIES} more_")

    if diff.libraries_removed:
        lines.append(f"\n- *Removed ({len(diff.libraries_removed)}):*")
        for c in sorted(diff.libraries_removed, key=lambda x: x.alias)[:_MAX_ENTRIES]:
            lines.append(f"• `{c.alias}` — {c.before_version}")
        if len(diff.libraries_removed) > _MAX_ENTRIES:
            lines.append(f"_…and {len(diff.libraries_removed) - _MAX_ENTRIES} more_")

    if diff.libraries_downgraded:
        lines.append(f"\n:rotating_light: *Downgraded ({len(diff.libraries_downgraded)}):*")
        for c in sorted(diff.libraries_downgraded, key=lambda x: x.alias):
            lines.append(f"• `{c.alias}` {c.before_version} → {c.after_version}")

    return {
        "type": "section",
        "text": {"type": "mrkdwn", "text": "\n".join(lines)},
    }


def _plugins_block(diff: FreezeDiff) -> dict[str, Any] | None:
    if not diff.plugin_changes:
        return None

    lines: list[str] = ["*:electric_plug: Plugins*"]
    for c in sorted(diff.plugin_changes, key=lambda x: x.alias):
        if c.before_version is None:
            lines.append(f"+ `{c.alias}` — {c.after_version}")
        elif c.after_version is None:
            lines.append(f"- `{c.alias}` — {c.before_version}")
        else:
            arrow = ":warning:" if c.bump is VersionBump.MAJOR else "↑"
            lines.append(f"{arrow} `{c.alias}` {c.before_version} → {c.after_version}")

    return {
        "type": "section",
        "text": {"type": "mrkdwn", "text": "\n".join(lines)},
    }


def _findings_block(diff: FreezeDiff) -> dict[str, Any]:
    if not diff.finding_changes:
        return {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": ":white_check_mark: *Catalog Health — no changes in findings*",
            },
        }

    lines: list[str] = ["*:stethoscope: Catalog Health*"]
    for f in diff.findings_introduced:
        emoji = _severity_emoji(f.severity)
        lines.append(f":new: {emoji} `{f.rule_id}` — {f.message}")
    for f in diff.findings_resolved:
        lines.append(f":white_check_mark: `{f.rule_id}` — {f.message} _(resolved)_")

    return {
        "type": "section",
        "text": {"type": "mrkdwn", "text": "\n".join(lines)},
    }
