"""Slack Block Kit report writer."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from gradle_deps_monitor.domain import FreezeReport
from gradle_deps_monitor.domain.advisory import AdvisorySeverity, LibraryAdvisory
from gradle_deps_monitor.domain.finding import Finding, Severity

# Maximum number of non-stable library entries shown in the Slack message.
_MAX_NON_STABLE = 10
# Maximum number of vulnerable library entries shown in the Slack message.
_MAX_VULN = 8

_SEVERITY_EMOJI = {
    Severity.ERROR: ":red_circle:",
    Severity.WARNING: ":warning:",
    Severity.INFO: ":information_source:",
    Severity.SUGGESTION: ":bulb:",
}


class SlackWriter:
    """Serialises a :class:`~gradle_deps_monitor.domain.FreezeReport` to Slack Block Kit JSON.

    The output is a Slack-friendly *summary* designed for posting via an
    incoming webhook. It focuses on non-stable versions and catalog health
    findings rather than listing every dependency.
    """

    def write(self, report: FreezeReport, dest: Path) -> None:
        """Write *report* as Block Kit JSON to *dest*."""
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(
            json.dumps(_build_payload(report), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )


# ---------------------------------------------------------------------------
# Block Kit helpers
# ---------------------------------------------------------------------------


def _build_payload(report: FreezeReport) -> dict[str, Any]:
    blocks: list[dict[str, Any]] = []
    blocks.append(_header_block())
    blocks.append(_meta_block(report))
    blocks.append(_stats_block(report))
    blocks.append({"type": "divider"})

    non_stable_block = _non_stable_block(report)
    if non_stable_block:
        blocks.append(non_stable_block)
        blocks.append({"type": "divider"})

    blocks.append(_health_block(list(report.health_findings)))

    security_block = _security_block(list(report.vulnerable_libraries), report)
    if security_block:
        blocks.append({"type": "divider"})
        blocks.append(security_block)

    return {"blocks": blocks}


def _header_block() -> dict[str, Any]:
    return {
        "type": "header",
        "text": {
            "type": "plain_text",
            "text": ":package: Gradle Dependency Freeze Report",
            "emoji": True,
        },
    }


def _meta_block(report: FreezeReport) -> dict[str, Any]:
    ts = report.generated_at.isoformat(timespec="seconds")
    catalog_name = report.catalog.source_path.name
    return {
        "type": "section",
        "fields": [
            {"type": "mrkdwn", "text": f"*Generated:*\n{ts}"},
            {"type": "mrkdwn", "text": f"*Catalog:*\n`{catalog_name}`"},
        ],
    }


def _stats_block(report: FreezeReport) -> dict[str, Any]:
    cat = report.catalog
    non_stable_count = sum(1 for lib in cat.libraries if not lib.version.is_stable)
    stable_count = cat.library_count - non_stable_count
    lib_text = f"*Libraries:*\n{cat.library_count}"
    if non_stable_count:
        lib_text += f" ({stable_count} stable, {non_stable_count} non-stable)"
    return {
        "type": "section",
        "fields": [
            {"type": "mrkdwn", "text": lib_text},
            {"type": "mrkdwn", "text": f"*Plugins:*\n{cat.plugin_count}"},
            {"type": "mrkdwn", "text": f"*Bundles:*\n{len(cat.bundles)}"},
        ],
    }


def _non_stable_block(report: FreezeReport) -> dict[str, Any] | None:
    non_stable = sorted(
        (lib for lib in report.catalog.libraries if not lib.version.is_stable),
        key=lambda lib: lib.alias,
    )
    if not non_stable:
        return None

    shown = non_stable[:_MAX_NON_STABLE]
    lines = [f"• `{lib.alias}` — {lib.version} _({lib.version.stability})_" for lib in shown]
    if len(non_stable) > _MAX_NON_STABLE:
        lines.append(f"_…and {len(non_stable) - _MAX_NON_STABLE} more_")

    count = len(non_stable)
    text = f"*:warning: Non-stable versions ({count}):*\n" + "\n".join(lines)
    return {"type": "section", "text": {"type": "mrkdwn", "text": text}}


_ADVISORY_EMOJI: dict[AdvisorySeverity, str] = {
    AdvisorySeverity.CRITICAL: ":red_circle:",
    AdvisorySeverity.HIGH: ":large_orange_circle:",
    AdvisorySeverity.MEDIUM: ":large_yellow_circle:",
    AdvisorySeverity.LOW: ":large_blue_circle:",
    AdvisorySeverity.UNKNOWN: ":white_circle:",
}


def _security_block(
    vulnerable: list[LibraryAdvisory],
    report: FreezeReport,
) -> dict[str, Any] | None:
    """Return a security block, or ``None`` when no scan was performed."""
    if not report.security_advisories:
        # Scanner was not configured — omit the section entirely.
        return None

    if not vulnerable:
        return {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": ":shield: *Security — No known vulnerabilities found*",
            },
        }

    shown = vulnerable[:_MAX_VULN]
    lines: list[str] = []
    for la in shown:
        top = la.max_severity
        emoji = _ADVISORY_EMOJI.get(top, ":white_circle:") if top else ":white_circle:"
        adv_ids = ", ".join(
            a.cve_id or a.ghsa_id for a in la.advisories if a.cve_id or a.ghsa_id
        )
        lines.append(f"{emoji} `{la.alias}` {la.version} — {adv_ids or 'advisory'}")
    if len(vulnerable) > _MAX_VULN:
        lines.append(f"_…and {len(vulnerable) - _MAX_VULN} more_")

    text = f":rotating_light: *Security — {len(vulnerable)} vulnerable librar{'y' if len(vulnerable) == 1 else 'ies'}:*\n"
    text += "\n".join(lines)
    return {"type": "section", "text": {"type": "mrkdwn", "text": text}}


def _health_block(findings: list[Finding]) -> dict[str, Any]:
    if not findings:
        return {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": ":white_check_mark: *Catalog Health — No issues found*",
            },
        }

    lines = [f"{_SEVERITY_EMOJI.get(f.severity, '')} `{f.rule_id}` — {f.message}" for f in findings]
    text = f"*:stethoscope: Catalog Health — {len(findings)} finding(s):*\n" + "\n".join(lines)
    return {"type": "section", "text": {"type": "mrkdwn", "text": text}}
