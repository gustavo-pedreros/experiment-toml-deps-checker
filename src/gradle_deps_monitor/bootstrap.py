"""Composition root.

Wires concrete infrastructure adapters into application use cases and
presentation command handlers. This is the only module permitted to import
from every layer; see ``docs/adr/0006-pragmatic-clean-architecture.md`` and
the import-linter contracts in ``pyproject.toml``.
"""

from __future__ import annotations

import os
from pathlib import Path

from gradle_deps_monitor.application.compute_freeze_diff import ComputeFreezeDiff
from gradle_deps_monitor.application.generate_freeze_report import GenerateFreezeReport
from gradle_deps_monitor.checks.runner import run_all as _run_health_checks
from gradle_deps_monitor.domain.config import AppConfig
from gradle_deps_monitor.infrastructure.checkers.library_health_checker import (
    LibraryHealthChecker,
)
from gradle_deps_monitor.infrastructure.checkers.play_store_compliance_checker import (
    PlayStoreComplianceChecker,
)
from gradle_deps_monitor.infrastructure.checkers.pom_license_checker import PomLicenseChecker
from gradle_deps_monitor.infrastructure.checkers.toolchain_compatibility_checker import (
    ToolchainCompatibilityChecker,
)
from gradle_deps_monitor.infrastructure.fetchers.changelog_fetcher import ChangelogFetcher
from gradle_deps_monitor.infrastructure.loaders.json_snapshot_loader import JsonSnapshotLoader
from gradle_deps_monitor.infrastructure.parsing.toml_catalog_parser import TomlCatalogParser
from gradle_deps_monitor.infrastructure.resolvers.maven_bom_resolver import MavenBomResolver
from gradle_deps_monitor.infrastructure.resolvers.maven_version_status_resolver import (
    MavenVersionStatusResolver,
)
from gradle_deps_monitor.infrastructure.scanners.composite_scanner import CompositeScanner
from gradle_deps_monitor.infrastructure.scanners.github_advisory_scanner import (
    GitHubAdvisoryScanner,
)
from gradle_deps_monitor.infrastructure.scanners.gradle_module_scanner import GradleModuleScanner
from gradle_deps_monitor.infrastructure.scanners.oss_index_scanner import OssIndexScanner
from gradle_deps_monitor.infrastructure.writers.diff_json_writer import DiffJsonWriter
from gradle_deps_monitor.infrastructure.writers.diff_markdown_writer import DiffMarkdownWriter
from gradle_deps_monitor.infrastructure.writers.diff_slack_writer import DiffSlackWriter
from gradle_deps_monitor.infrastructure.writers.findings_csv_writer import FindingsCsvWriter
from gradle_deps_monitor.infrastructure.writers.inventory_csv_writer import InventoryCsvWriter
from gradle_deps_monitor.infrastructure.writers.json_writer import JsonWriter
from gradle_deps_monitor.infrastructure.writers.markdown_writer import MarkdownWriter
from gradle_deps_monitor.infrastructure.writers.slack_writer import SlackWriter
from gradle_deps_monitor.presentation.commands.check_command import CheckCommand
from gradle_deps_monitor.presentation.commands.diff_command import DiffCommand

# Default stem for freeze report output files.
_REPORT_STEM = "freeze"
# Default stem for diff report output files.
_DIFF_STEM = "freeze-diff"

# On-disk cache for HTTP fetches (Maven metadata, advisory queries).
# Reusing a single root directory keeps unrelated runs from invalidating
# each other and matches the convention used by the OSS Index and GitHub
# Advisory adapters.
_CACHE_ROOT = Path.home() / ".cache" / "gradle-deps-monitor"


def _build_scanner() -> CompositeScanner | GitHubAdvisoryScanner | OssIndexScanner | None:
    """Return the best available vulnerability scanner based on env vars.

    Priority:
    1. Both GitHub token AND OSS Index credentials → :class:`CompositeScanner`
    2. GitHub token only → :class:`GitHubAdvisoryScanner`
    3. OSS Index credentials only → :class:`OssIndexScanner`
    4. No credentials → ``None`` (security section omitted from reports)
    """
    gh_token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    oss_user = os.environ.get("OSSINDEX_USER")
    oss_key = os.environ.get("OSSINDEX_API_KEY")

    gh_scanner = GitHubAdvisoryScanner(token=gh_token) if gh_token else None
    has_oss_creds = bool(oss_user and oss_key)
    oss_scanner = OssIndexScanner(username=oss_user, api_key=oss_key) if has_oss_creds else None

    if gh_scanner and oss_scanner:
        return CompositeScanner(scanners=(gh_scanner, oss_scanner))
    return gh_scanner or oss_scanner


def create_check_command(
    *,
    module_usage: bool = False,
    risk_score: bool = False,
    app_config: AppConfig | None = None,
) -> CheckCommand:
    """Return a fully wired :class:`~...presentation.commands.check_command.CheckCommand`.

    :param module_usage: When ``True``, wire a
        :class:`~...infrastructure.scanners.gradle_module_scanner.GradleModuleScanner`
        into the use case so that module usage data is included in reports.
        Defaults to ``False`` (opt-in, slower on large projects).
    :param risk_score: When ``True``, enable the RFC-0008 composite risk score
        computation (opt-in; experimental — see ADR-0004).
        Defaults to ``False``.
    :param app_config: RFC-0012 application configuration. When ``None``,
        defaults are used. The ``risk_weights`` and ``risk_thresholds``
        sections are forwarded to the risk score; other sections are
        reserved for future RFCs.

    Concrete adapters created here:

    - :class:`~...infrastructure.parsing.toml_catalog_parser.TomlCatalogParser`
    - :class:`~...infrastructure.writers.markdown_writer.MarkdownWriter`
    - :class:`~...infrastructure.writers.json_writer.JsonWriter`
    - :class:`~...infrastructure.writers.slack_writer.SlackWriter`
    - :class:`~...infrastructure.writers.inventory_csv_writer.InventoryCsvWriter`
    - :class:`~...infrastructure.writers.findings_csv_writer.FindingsCsvWriter`
    """
    cfg = app_config or AppConfig()
    parser = TomlCatalogParser()
    scanner = _build_scanner()
    gh_token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    version_status_resolver = MavenVersionStatusResolver(cache_dir=_CACHE_ROOT / "maven")
    bom_resolver = MavenBomResolver()
    use_case = GenerateFreezeReport(
        catalog_parser=parser,
        health_checker=_run_health_checks,
        vulnerability_scanner=scanner,
        compliance_checker=PlayStoreComplianceChecker(),
        toolchain_checker=ToolchainCompatibilityChecker(),
        library_health_checker=LibraryHealthChecker(),
        changelog_fetcher=ChangelogFetcher(github_token=gh_token),
        module_usage_scanner=GradleModuleScanner() if module_usage else None,
        license_checker=PomLicenseChecker(),
        version_status_resolver=version_status_resolver,
        bom_resolver=bom_resolver,
        enable_risk_score=risk_score,
        risk_weights=cfg.risk_weights,
        risk_thresholds=cfg.risk_thresholds,
    )
    return CheckCommand(
        use_case=use_case,
        writers=[
            (f"{_REPORT_STEM}.md", MarkdownWriter()),
            (f"{_REPORT_STEM}.json", JsonWriter()),
            (f"{_REPORT_STEM}-slack.json", SlackWriter()),
            (f"{_REPORT_STEM}-inventory.csv", InventoryCsvWriter()),
            (f"{_REPORT_STEM}-findings.csv", FindingsCsvWriter()),
        ],
    )


def create_diff_command() -> DiffCommand:
    """Return a fully wired :class:`~...presentation.commands.diff_command.DiffCommand`.

    Concrete adapters created here:

    - :class:`~...infrastructure.loaders.json_snapshot_loader.JsonSnapshotLoader`
    - :class:`~...infrastructure.writers.diff_markdown_writer.DiffMarkdownWriter`
    - :class:`~...infrastructure.writers.diff_json_writer.DiffJsonWriter`
    - :class:`~...infrastructure.writers.diff_slack_writer.DiffSlackWriter`
    """
    return DiffCommand(
        use_case=ComputeFreezeDiff(),
        loader=JsonSnapshotLoader(),
        writers=[
            (f"{_DIFF_STEM}.md", DiffMarkdownWriter()),
            (f"{_DIFF_STEM}.json", DiffJsonWriter()),
            (f"{_DIFF_STEM}-slack.json", DiffSlackWriter()),
        ],
    )
