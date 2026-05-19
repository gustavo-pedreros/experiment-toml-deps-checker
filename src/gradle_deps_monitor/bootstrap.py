"""Composition root.

Wires concrete infrastructure adapters into application use cases and
presentation command handlers. This is the only module permitted to import
from every layer; see ``docs/adr/0006-pragmatic-clean-architecture.md`` and
the import-linter contracts in ``pyproject.toml``.
"""

from __future__ import annotations

import atexit
import os
import shutil
from pathlib import Path
from typing import Any

from gradle_deps_monitor.application.compute_freeze_diff import ComputeFreezeDiff
from gradle_deps_monitor.application.generate_freeze_report import GenerateFreezeReport
from gradle_deps_monitor.checks.runner import run_all as _run_health_checks
from gradle_deps_monitor.domain.config import AppConfig
from gradle_deps_monitor.infrastructure.cache.cache_paths import (
    clear_cache,
    ephemeral_cache_root,
    resolve_cache_root,
)
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


def _build_scanner(
    cache_root: Path, ttl_advisory: int
) -> CompositeScanner | GitHubAdvisoryScanner | OssIndexScanner | None:
    """Return the best available vulnerability scanner based on env vars.

    Priority:
    1. Both GitHub token AND OSS Index credentials → :class:`CompositeScanner`
    2. GitHub token only → :class:`GitHubAdvisoryScanner`
    3. OSS Index credentials only → :class:`OssIndexScanner`
    4. No credentials → ``None`` (security section omitted from reports)

    Both scanners receive ``cache_root / "ghsa"`` / ``cache_root / "ossindex"``
    so the persistent cache always lives under the resolved cache root
    (RFC-0029). Prior to RFC-0029 the scanners silently fell back to
    constructor defaults of ``.cache/ghsa`` / ``.cache/ossindex`` relative
    to CWD, splitting cache state across three different directories.
    """
    gh_token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    oss_user = os.environ.get("OSSINDEX_USER")
    oss_key = os.environ.get("OSSINDEX_API_KEY")

    gh_scanner = (
        GitHubAdvisoryScanner(token=gh_token, cache_dir=cache_root / "ghsa", ttl=ttl_advisory)
        if gh_token
        else None
    )
    has_oss_creds = bool(oss_user and oss_key)
    oss_scanner = (
        OssIndexScanner(
            username=oss_user, api_key=oss_key, cache_dir=cache_root / "ossindex", ttl=ttl_advisory
        )
        if has_oss_creds
        else None
    )

    if gh_scanner and oss_scanner:
        return CompositeScanner(scanners=(gh_scanner, oss_scanner))
    return gh_scanner or oss_scanner


def _prepare_cache_root(app_config: AppConfig, *, no_cache: bool, clear_cache_first: bool) -> Path:
    """Apply the RFC-0029 cache-root resolution + lifecycle flags.

    Returns the cache root the adapters should use for this run:

    - ``no_cache=True`` → :func:`ephemeral_cache_root` (tempdir),
      cleaned up at process exit. The persistent cache is left
      untouched.
    - ``clear_cache_first=True`` and not ``no_cache`` →
      :func:`clear_cache` against the resolved persistent root,
      then return that same root for the adapters to rebuild into.
    - otherwise → the resolved persistent root.
    """
    if no_cache:
        ephemeral = ephemeral_cache_root()
        atexit.register(shutil.rmtree, ephemeral, ignore_errors=True)
        return ephemeral

    persistent = resolve_cache_root(app_config.cache)
    if clear_cache_first:
        clear_cache(persistent)
    return persistent


def create_check_command(
    *,
    module_usage: bool = False,
    risk_score: bool = False,
    app_config: AppConfig | None = None,
    no_cache: bool = False,
    clear_cache_first: bool = False,
    cache_ttl_override: int | None = None,
    slack: bool | None = None,
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
        defaults are used. The ``risk_weights``, ``risk_thresholds``,
        ``cache``, and ``output`` sections are forwarded; other sections
        are reserved for future RFCs.
    :param no_cache: RFC-0029 — bypass the persistent cache for this run.
        The adapters write to an ephemeral tempdir cleaned up at exit;
        the persistent cache is left untouched.
    :param clear_cache_first: RFC-0029 — purge the persistent cache
        before constructing adapters. No-op when ``no_cache=True``.
    :param cache_ttl_override: RFC-0029 — when not ``None``, applies the
        same TTL to every adapter (overrides per-source defaults).
    :param slack: RFC-0034 — when ``True``, include ``SlackWriter`` in
        the writers list. When ``None`` (default), defer to
        ``app_config.output.slack`` (which defaults to ``False``).
        The CLI flag wins over the config file.

    Concrete adapters created here:

    - :class:`~...infrastructure.parsing.toml_catalog_parser.TomlCatalogParser`
    - :class:`~...infrastructure.writers.markdown_writer.MarkdownWriter`
    - :class:`~...infrastructure.writers.json_writer.JsonWriter`
    - :class:`~...infrastructure.writers.slack_writer.SlackWriter`
      *(only when ``slack=True`` or ``[output] slack = true``)*
    - :class:`~...infrastructure.writers.inventory_csv_writer.InventoryCsvWriter`
    - :class:`~...infrastructure.writers.findings_csv_writer.FindingsCsvWriter`
    """
    cfg = app_config or AppConfig()
    cache_root = _prepare_cache_root(cfg, no_cache=no_cache, clear_cache_first=clear_cache_first)
    ttl_maven = (
        cache_ttl_override if cache_ttl_override is not None else cfg.cache.ttl_seconds_maven
    )
    ttl_advisory = (
        cache_ttl_override if cache_ttl_override is not None else cfg.cache.ttl_seconds_advisory
    )
    parser = TomlCatalogParser()
    scanner = _build_scanner(cache_root, ttl_advisory)
    gh_token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    version_status_resolver = MavenVersionStatusResolver(
        cache_dir=cache_root / "maven", ttl=ttl_maven
    )
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
    slack_enabled = slack if slack is not None else cfg.output.slack
    writers: list[tuple[str, Any]] = [
        (f"{_REPORT_STEM}.md", MarkdownWriter()),
        (f"{_REPORT_STEM}.json", JsonWriter()),
        (f"{_REPORT_STEM}-inventory.csv", InventoryCsvWriter()),
        (f"{_REPORT_STEM}-findings.csv", FindingsCsvWriter()),
    ]
    if slack_enabled:
        # Insert Slack between json and the CSVs so the file listing
        # mirrors the historical order when --slack is passed.
        writers.insert(2, (f"{_REPORT_STEM}-slack.json", SlackWriter()))
    return CheckCommand(use_case=use_case, writers=writers)


def create_diff_command(
    *,
    app_config: AppConfig | None = None,
    slack: bool | None = None,
) -> DiffCommand:
    """Return a fully wired :class:`~...presentation.commands.diff_command.DiffCommand`.

    :param app_config: RFC-0012 application configuration. When ``None``,
        defaults are used. Only the ``output`` section is consumed here
        (other sections are check-only).
    :param slack: RFC-0034 — when ``True``, include ``DiffSlackWriter``
        in the writers list. When ``None`` (default), defer to
        ``app_config.output.slack`` (which defaults to ``False``).
        The CLI flag wins over the config file.

    Concrete adapters created here:

    - :class:`~...infrastructure.loaders.json_snapshot_loader.JsonSnapshotLoader`
    - :class:`~...infrastructure.writers.diff_markdown_writer.DiffMarkdownWriter`
    - :class:`~...infrastructure.writers.diff_json_writer.DiffJsonWriter`
    - :class:`~...infrastructure.writers.diff_slack_writer.DiffSlackWriter`
      *(only when ``slack=True`` or ``[output] slack = true``)*
    """
    cfg = app_config or AppConfig()
    slack_enabled = slack if slack is not None else cfg.output.slack
    writers: list[tuple[str, Any]] = [
        (f"{_DIFF_STEM}.md", DiffMarkdownWriter()),
        (f"{_DIFF_STEM}.json", DiffJsonWriter()),
    ]
    if slack_enabled:
        writers.append((f"{_DIFF_STEM}-slack.json", DiffSlackWriter()))
    return DiffCommand(
        use_case=ComputeFreezeDiff(),
        loader=JsonSnapshotLoader(),
        writers=writers,
    )
