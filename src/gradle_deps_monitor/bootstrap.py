"""Composition root.

Wires concrete infrastructure adapters into application use cases and
presentation command handlers. This is the only module permitted to import
from every layer; see ``docs/adr/0006-pragmatic-clean-architecture.md`` and
the import-linter contracts in ``pyproject.toml``.
"""

from __future__ import annotations

import os

from gradle_deps_monitor.application.compute_freeze_diff import ComputeFreezeDiff
from gradle_deps_monitor.application.generate_freeze_report import GenerateFreezeReport
from gradle_deps_monitor.checks.runner import run_all as _run_health_checks
from gradle_deps_monitor.infrastructure.checkers.library_health_checker import (
    LibraryHealthChecker,
)
from gradle_deps_monitor.infrastructure.checkers.play_store_compliance_checker import (
    PlayStoreComplianceChecker,
)
from gradle_deps_monitor.infrastructure.checkers.toolchain_compatibility_checker import (
    ToolchainCompatibilityChecker,
)
from gradle_deps_monitor.infrastructure.fetchers.changelog_fetcher import ChangelogFetcher
from gradle_deps_monitor.infrastructure.loaders.json_snapshot_loader import JsonSnapshotLoader
from gradle_deps_monitor.infrastructure.parsing.toml_catalog_parser import TomlCatalogParser
from gradle_deps_monitor.infrastructure.scanners.composite_scanner import CompositeScanner
from gradle_deps_monitor.infrastructure.scanners.github_advisory_scanner import (
    GitHubAdvisoryScanner,
)
from gradle_deps_monitor.infrastructure.scanners.gradle_module_scanner import GradleModuleScanner
from gradle_deps_monitor.infrastructure.scanners.oss_index_scanner import OssIndexScanner
from gradle_deps_monitor.infrastructure.writers.diff_json_writer import DiffJsonWriter
from gradle_deps_monitor.infrastructure.writers.diff_markdown_writer import DiffMarkdownWriter
from gradle_deps_monitor.infrastructure.writers.diff_slack_writer import DiffSlackWriter
from gradle_deps_monitor.infrastructure.writers.json_writer import JsonWriter
from gradle_deps_monitor.infrastructure.writers.markdown_writer import MarkdownWriter
from gradle_deps_monitor.infrastructure.writers.slack_writer import SlackWriter
from gradle_deps_monitor.presentation.commands.check_command import CheckCommand
from gradle_deps_monitor.presentation.commands.diff_command import DiffCommand

# Default stem for freeze report output files.
_REPORT_STEM = "freeze"
# Default stem for diff report output files.
_DIFF_STEM = "freeze-diff"


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


def create_check_command(*, module_usage: bool = False) -> CheckCommand:
    """Return a fully wired :class:`~...presentation.commands.check_command.CheckCommand`.

    :param module_usage: When ``True``, wire a
        :class:`~...infrastructure.scanners.gradle_module_scanner.GradleModuleScanner`
        into the use case so that module usage data is included in reports.
        Defaults to ``False`` (opt-in, slower on large projects).

    Concrete adapters created here:

    - :class:`~...infrastructure.parsing.toml_catalog_parser.TomlCatalogParser`
    - :class:`~...infrastructure.writers.markdown_writer.MarkdownWriter`
    - :class:`~...infrastructure.writers.json_writer.JsonWriter`
    - :class:`~...infrastructure.writers.slack_writer.SlackWriter`
    """
    parser = TomlCatalogParser()
    scanner = _build_scanner()
    gh_token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    use_case = GenerateFreezeReport(
        catalog_parser=parser,
        health_checker=_run_health_checks,
        vulnerability_scanner=scanner,
        compliance_checker=PlayStoreComplianceChecker(),
        toolchain_checker=ToolchainCompatibilityChecker(),
        library_health_checker=LibraryHealthChecker(),
        changelog_fetcher=ChangelogFetcher(github_token=gh_token),
        module_usage_scanner=GradleModuleScanner() if module_usage else None,
    )
    return CheckCommand(
        use_case=use_case,
        writers=[
            (f"{_REPORT_STEM}.md", MarkdownWriter()),
            (f"{_REPORT_STEM}.json", JsonWriter()),
            (f"{_REPORT_STEM}-slack.json", SlackWriter()),
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
