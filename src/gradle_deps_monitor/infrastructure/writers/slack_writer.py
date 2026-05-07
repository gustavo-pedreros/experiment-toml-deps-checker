"""Slack Block Kit report writer."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from gradle_deps_monitor.domain import FreezeReport
from gradle_deps_monitor.domain.advisory import LibraryAdvisory
from gradle_deps_monitor.domain.changelog import BreakingSignal, ChangelogEntry
from gradle_deps_monitor.domain.compliance import ComplianceFinding
from gradle_deps_monitor.domain.finding import Finding
from gradle_deps_monitor.domain.library_health import LibraryHealthFinding
from gradle_deps_monitor.domain.license import LicenseAudit, LicenseTier
from gradle_deps_monitor.domain.module_usage import ModuleUsageMap
from gradle_deps_monitor.domain.risk_score import RiskLevel, RiskScoreReport
from gradle_deps_monitor.domain.severity_style import style_for
from gradle_deps_monitor.domain.toolchain import ToolchainFinding

# Maximum number of non-stable library entries shown in the Slack message.
_MAX_NON_STABLE = 10
# Maximum number of vulnerable library entries shown in the Slack message.
_MAX_VULN = 8


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

    outdated_block = _outdated_block(report)
    if outdated_block:
        blocks.append(outdated_block)
        blocks.append({"type": "divider"})

    bom_block = _bom_block(report)
    if bom_block:
        blocks.append(bom_block)
        blocks.append({"type": "divider"})

    blocks.append(_health_block(list(report.health_findings)))

    security_block = _security_block(list(report.vulnerable_libraries), report)
    if security_block:
        blocks.append({"type": "divider"})
        blocks.append(security_block)

    compliance_block = _compliance_block(list(report.compliance_findings))
    if compliance_block:
        blocks.append({"type": "divider"})
        blocks.append(compliance_block)

    toolchain_block = _toolchain_block(list(report.toolchain_findings))
    if toolchain_block:
        blocks.append({"type": "divider"})
        blocks.append(toolchain_block)

    library_health_block = _library_health_block(list(report.library_health_findings))
    if library_health_block:
        blocks.append({"type": "divider"})
        blocks.append(library_health_block)

    changelog_block = _changelog_block(list(report.changelog_entries))
    if changelog_block:
        blocks.append({"type": "divider"})
        blocks.append(changelog_block)

    module_block = _module_usage_block(report.module_usage_map)
    if module_block:
        blocks.append({"type": "divider"})
        blocks.append(module_block)

    license_block = _license_block(report.license_audit)
    if license_block:
        blocks.append({"type": "divider"})
        blocks.append(license_block)

    risk_block = _risk_score_block(report.risk_score_report)
    if risk_block:
        blocks.append({"type": "divider"})
        blocks.append(risk_block)

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


def _outdated_block(report: FreezeReport) -> dict[str, Any] | None:
    if not report.library_version_statuses:
        return None
    outdated = report.outdated_libraries
    if not outdated:
        return None
    text = (
        f"*:up: Outdated libraries ({len(outdated)}):* "
        f"{report.major_outdated_count} major, "
        f"{report.minor_outdated_count} minor, "
        f"{report.patch_outdated_count} patch"
    )
    return {"type": "section", "text": {"type": "mrkdwn", "text": text}}


def _bom_block(report: FreezeReport) -> dict[str, Any] | None:
    if not report.bom_resolutions:
        return None
    children_count_by_bom: dict[str, int] = {}
    for lib in report.catalog.libraries:
        if lib.bom_alias:
            children_count_by_bom[lib.bom_alias] = children_count_by_bom.get(lib.bom_alias, 0) + 1
    lines = [
        f"• `{r.bom_alias}` `{r.bom_version}` "
        f"— manages {len(r.managed)} (catalog uses {children_count_by_bom.get(r.bom_alias, 0)})"
        for r in report.bom_resolutions
    ]
    text = f"*:bookmark_tabs: BoMs ({len(report.bom_resolutions)}):*\n" + "\n".join(lines)
    return {"type": "section", "text": {"type": "mrkdwn", "text": text}}


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
        emoji = style_for(top.to_common()).slack_emoji if top else ":white_circle:"
        adv_ids = ", ".join(a.cve_id or a.ghsa_id for a in la.advisories if a.cve_id or a.ghsa_id)
        lines.append(f"{emoji} `{la.alias}` {la.version} — {adv_ids or 'advisory'}")
    if len(vulnerable) > _MAX_VULN:
        lines.append(f"_…and {len(vulnerable) - _MAX_VULN} more_")

    noun = "library" if len(vulnerable) == 1 else "libraries"
    text = f":rotating_light: *Security — {len(vulnerable)} vulnerable {noun}:*\n"
    text += "\n".join(lines)
    return {"type": "section", "text": {"type": "mrkdwn", "text": text}}


# Maximum compliance findings shown in Slack.
_MAX_COMPLIANCE = 8


def _compliance_block(findings: list[ComplianceFinding]) -> dict[str, Any] | None:
    """Return a compliance block, or ``None`` when there are no findings."""
    if not findings:
        return None

    shown = findings[:_MAX_COMPLIANCE]
    lines: list[str] = []
    for f in shown:
        emoji = style_for(f.severity.to_common()).slack_emoji
        deadline = f" (deadline: {f.deadline})" if f.deadline else ""
        # RFC-0015: surface the library alias when the finding is attributed,
        # so reviewers know which catalog entry to bump.
        alias = f" `{f.alias}` —" if f.alias else ""
        lines.append(f"{emoji} `{f.rule_id}`{alias} {f.message}{deadline}")
    if len(findings) > _MAX_COMPLIANCE:
        lines.append(f"_…and {len(findings) - _MAX_COMPLIANCE} more_")

    noun = "finding" if len(findings) == 1 else "findings"
    text = f":store: *Play Store Compliance — {len(findings)} {noun}:*\n"
    text += "\n".join(lines)
    return {"type": "section", "text": {"type": "mrkdwn", "text": text}}


# Maximum toolchain findings shown in Slack.
_MAX_TOOLCHAIN = 8


def _toolchain_block(findings: list[ToolchainFinding]) -> dict[str, Any] | None:
    """Return a toolchain block, or ``None`` when there are no findings."""
    if not findings:
        return None

    shown = findings[:_MAX_TOOLCHAIN]
    lines: list[str] = []
    for f in shown:
        emoji = style_for(f.severity.to_common()).slack_emoji
        lines.append(f"{emoji} `{f.rule_id}` — {f.message}")
    if len(findings) > _MAX_TOOLCHAIN:
        lines.append(f"_…and {len(findings) - _MAX_TOOLCHAIN} more_")

    noun = "finding" if len(findings) == 1 else "findings"
    text = f":wrench: *Toolchain Compatibility — {len(findings)} {noun}:*\n"
    text += "\n".join(lines)
    return {"type": "section", "text": {"type": "mrkdwn", "text": text}}


# Maximum library health findings shown in Slack.
_MAX_LIBRARY_HEALTH = 8


def _library_health_block(findings: list[LibraryHealthFinding]) -> dict[str, Any] | None:
    """Return a library health block, or ``None`` when there are no findings."""
    if not findings:
        return None

    shown = sorted(findings, key=lambda f: (f.severity, f.alias))[:_MAX_LIBRARY_HEALTH]
    lines: list[str] = []
    for f in shown:
        emoji = style_for(f.severity.to_common()).slack_emoji
        replacement = f" → `{f.replacement}`" if f.replacement else ""
        lines.append(f"{emoji} `{f.alias}` ({f.signal.upper()}) — {f.message}{replacement}")
    if len(findings) > _MAX_LIBRARY_HEALTH:
        lines.append(f"_…and {len(findings) - _MAX_LIBRARY_HEALTH} more_")

    noun = "finding" if len(findings) == 1 else "findings"
    text = f":pill: *Library Health — {len(findings)} {noun}:*\n"
    text += "\n".join(lines)
    return {"type": "section", "text": {"type": "mrkdwn", "text": text}}


_BREAKING_SIGNAL_EMOJI: dict[BreakingSignal, str] = {
    BreakingSignal.LIKELY: ":red_circle:",
    BreakingSignal.CLEAN: ":large_green_circle:",
    BreakingSignal.UNKNOWN: ":white_circle:",
}
# Maximum changelog entries shown in Slack.
_MAX_CHANGELOG = 8


def _changelog_block(entries: list[ChangelogEntry]) -> dict[str, Any] | None:
    """Return a major-upgrades block, or ``None`` when there are no entries."""
    if not entries:
        return None

    shown = sorted(entries, key=lambda e: e.alias)[:_MAX_CHANGELOG]
    lines: list[str] = []
    for e in shown:
        emoji = _BREAKING_SIGNAL_EMOJI.get(e.breaking_signal, ":white_circle:")
        link = f" <{e.changelog_url}|release notes>" if e.changelog_url else ""
        lines.append(f"{emoji} `{e.alias}` {e.pinned_version} → *{e.latest_version}*{link}")
    if len(entries) > _MAX_CHANGELOG:
        lines.append(f"_…and {len(entries) - _MAX_CHANGELOG} more_")

    noun = "upgrade" if len(entries) == 1 else "upgrades"
    text = f":arrow_up: *Major Upgrades Available — {len(entries)} {noun}:*\n"
    text += "\n".join(lines)
    return {"type": "section", "text": {"type": "mrkdwn", "text": text}}


# Maximum module usage entries shown in Slack.
_MAX_MODULE_USAGE = 8


def _module_usage_block(usage_map: ModuleUsageMap | None) -> dict[str, Any] | None:
    """Return a module usage summary block, or ``None`` when scan was not run."""
    if usage_map is None:
        return None

    in_use = list(usage_map.libraries_in_use())
    top_mods = list(usage_map.top_modules(5))

    lib_lines = [
        f"• `{u.alias}` — {u.direct_count} direct"
        + (f", {u.api_count} via api" if u.api_count else "")
        for u in sorted(in_use, key=lambda x: -x.direct_count)[:_MAX_MODULE_USAGE]
    ]
    if len(in_use) > _MAX_MODULE_USAGE:
        lib_lines.append(f"_…and {len(in_use) - _MAX_MODULE_USAGE} more_")

    mod_lines = [f"• `{m.module_path}` — {m.direct_dep_count} deps" for m in top_mods]

    text = (
        f":world_map: *Module Usage Map — {usage_map.modules_scanned} modules scanned:*\n"
        + "\n".join(lib_lines)
    )
    if mod_lines:
        text += "\n\n*Top modules by dep count:*\n" + "\n".join(mod_lines)

    return {"type": "section", "text": {"type": "mrkdwn", "text": text}}


_LICENSE_TIER_EMOJI: dict[LicenseTier, str] = {
    LicenseTier.PERMISSIVE: ":white_check_mark:",
    LicenseTier.WEAK_COPYLEFT: ":warning:",
    LicenseTier.STRONG_COPYLEFT: ":red_circle:",
    LicenseTier.UNKNOWN: ":question:",
}
# Maximum license findings shown in Slack.
_MAX_LICENSE = 8


def _license_block(audit: LicenseAudit | None) -> dict[str, Any] | None:
    """Return a license audit block, or ``None`` when no audit was run."""
    if audit is None:
        return None

    if not audit.findings:
        text = (
            f":scales: *License Audit — {audit.libraries_audited} "
            f"{'library' if audit.libraries_audited == 1 else 'libraries'} audited, "
            "all permissive*"
        )
        return {"type": "section", "text": {"type": "mrkdwn", "text": text}}

    shown = audit.findings[:_MAX_LICENSE]
    lines: list[str] = []
    for f in shown:
        emoji = _LICENSE_TIER_EMOJI.get(f.tier, ":question:")
        lic = f.license_name or "_not declared_"
        lines.append(f"{emoji} `{f.alias}` — {lic} ({f.tier.value.replace('_', ' ')})")
    if audit.flagged_count > _MAX_LICENSE:
        lines.append(f"_…and {audit.flagged_count - _MAX_LICENSE} more_")
    if audit.permissive_count > 0:
        lines.append(
            f":white_check_mark: {audit.permissive_count} "
            f"{'library' if audit.permissive_count == 1 else 'libraries'} permissive"
        )

    text = (
        f":scales: *License Audit — {audit.flagged_count} flagged "
        f"({audit.libraries_audited} total):*\n" + "\n".join(lines)
    )
    return {"type": "section", "text": {"type": "mrkdwn", "text": text}}


_RISK_LEVEL_EMOJI: dict[RiskLevel, str] = {
    RiskLevel.CRITICAL: ":red_circle:",
    RiskLevel.HIGH: ":large_orange_circle:",
    RiskLevel.MEDIUM: ":large_yellow_circle:",
    RiskLevel.LOW: ":large_blue_circle:",
    RiskLevel.NONE: ":white_circle:",
}
# Maximum risk entries shown in Slack.
_MAX_RISK = 5


def _risk_score_block(rsr: RiskScoreReport | None) -> dict[str, Any] | None:
    """Return a risk score summary block, or ``None`` when not enabled."""
    if rsr is None:
        return None

    top = rsr.top[:_MAX_RISK]
    if not top:
        text = (
            f":bar_chart: *Risk Score (experimental) — {rsr.libraries_scored} "
            f"{'library' if rsr.libraries_scored == 1 else 'libraries'} scored, "
            "no risk signals detected*"
        )
        return {"type": "section", "text": {"type": "mrkdwn", "text": text}}

    lines: list[str] = []
    for lib in top:
        emoji = _RISK_LEVEL_EMOJI.get(lib.level, ":white_circle:")
        level_label = lib.level.upper()
        lines.append(f"{emoji} `{lib.alias}` {lib.version} — *{lib.total_score}* ({level_label})")
    if len(rsr.scored_libraries) > _MAX_RISK:
        lines.append(f"_…and {len(rsr.scored_libraries) - _MAX_RISK} more with non-zero score_")

    noun = "library" if len(rsr.scored_libraries) == 1 else "libraries"
    text = (
        f":bar_chart: *Risk Score (experimental) — top {len(top)} of "
        f"{len(rsr.scored_libraries)} {noun} with non-zero score:*\n"
        + "\n".join(lines)
        + f"\n_avg {rsr.avg_score:.1f} · max {rsr.max_score}_"
    )
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

    lines = [
        f"{style_for(f.severity.to_common()).slack_emoji} `{f.rule_id}` — {f.message}"
        for f in findings
    ]
    text = f"*:stethoscope: Catalog Health — {len(findings)} finding(s):*\n" + "\n".join(lines)
    return {"type": "section", "text": {"type": "mrkdwn", "text": text}}
