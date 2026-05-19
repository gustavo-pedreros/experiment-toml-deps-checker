"""Composition-root tests (RFC-0031).

Verifies the wiring contract of ``bootstrap.create_check_command`` and
``bootstrap.create_diff_command`` without exercising the wired-up
adapters at runtime. All cache writes are redirected to ``tmp_path``
via :envvar:`GRADLE_DEPS_MONITOR_CACHE_ROOT` so no real
``~/.cache/gradle-deps-monitor`` pollution happens during the test run.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from gradle_deps_monitor import bootstrap
from gradle_deps_monitor.domain.config import AppConfig, CacheConfig
from gradle_deps_monitor.infrastructure.cache.cache_paths import CACHE_ROOT_ENV_VAR
from gradle_deps_monitor.infrastructure.loaders.json_snapshot_loader import JsonSnapshotLoader
from gradle_deps_monitor.infrastructure.scanners.composite_scanner import CompositeScanner
from gradle_deps_monitor.infrastructure.scanners.github_advisory_scanner import (
    GitHubAdvisoryScanner,
)
from gradle_deps_monitor.infrastructure.scanners.oss_index_scanner import OssIndexScanner

# Credential env vars cleared in every test so the host environment never leaks.
_CRED_ENVS = ("GITHUB_TOKEN", "GH_TOKEN", "OSSINDEX_USER", "OSSINDEX_API_KEY")


@pytest.fixture(autouse=True)
def _isolate_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Redirect cache writes and clear credential env vars per-test."""
    monkeypatch.setenv(CACHE_ROOT_ENV_VAR, str(tmp_path / "cache"))
    for name in _CRED_ENVS:
        monkeypatch.delenv(name, raising=False)


# ---------------------------------------------------------------------------
# _build_scanner — credential-driven selection
# ---------------------------------------------------------------------------


class TestBuildScanner:
    def test_no_credentials_returns_none(self, tmp_path: Path) -> None:
        scanner = bootstrap._build_scanner(tmp_path, ttl_advisory=86_400)
        assert scanner is None

    def test_github_token_only_returns_ghsa(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_xxx")
        scanner = bootstrap._build_scanner(tmp_path, ttl_advisory=86_400)
        assert isinstance(scanner, GitHubAdvisoryScanner)

    def test_gh_token_alias_works(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """``GH_TOKEN`` is the documented alias for ``GITHUB_TOKEN``."""
        monkeypatch.setenv("GH_TOKEN", "ghp_xxx")
        scanner = bootstrap._build_scanner(tmp_path, ttl_advisory=86_400)
        assert isinstance(scanner, GitHubAdvisoryScanner)

    def test_oss_only_returns_oss(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OSSINDEX_USER", "user@example.com")
        monkeypatch.setenv("OSSINDEX_API_KEY", "key-xxx")
        scanner = bootstrap._build_scanner(tmp_path, ttl_advisory=86_400)
        assert isinstance(scanner, OssIndexScanner)

    def test_both_credentials_return_composite(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_xxx")
        monkeypatch.setenv("OSSINDEX_USER", "user@example.com")
        monkeypatch.setenv("OSSINDEX_API_KEY", "key-xxx")
        scanner = bootstrap._build_scanner(tmp_path, ttl_advisory=86_400)
        assert isinstance(scanner, CompositeScanner)


# ---------------------------------------------------------------------------
# _prepare_cache_root — RFC-0029 lifecycle flags
# ---------------------------------------------------------------------------


class TestPrepareCacheRoot:
    def test_default_resolves_to_env_var_target(self, tmp_path: Path) -> None:
        """The autouse fixture sets the env var to ``tmp_path/cache``."""
        root = bootstrap._prepare_cache_root(AppConfig(), no_cache=False, clear_cache_first=False)
        assert root == tmp_path / "cache"

    def test_no_cache_returns_ephemeral(self, tmp_path: Path) -> None:
        ephemeral = bootstrap._prepare_cache_root(
            AppConfig(), no_cache=True, clear_cache_first=False
        )
        assert ephemeral != tmp_path / "cache"
        assert ephemeral.is_dir()
        assert "gradle-deps-monitor-nocache-" in ephemeral.name

    def test_clear_cache_first_purges_existing(self, tmp_path: Path) -> None:
        cache_root = tmp_path / "cache"
        cache_root.mkdir(parents=True)
        (cache_root / "stale-entry").write_text("garbage")

        returned = bootstrap._prepare_cache_root(
            AppConfig(), no_cache=False, clear_cache_first=True
        )

        assert returned == cache_root
        assert not (cache_root / "stale-entry").exists()

    def test_explicit_config_root_used_when_env_unset(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Without the env var, ``[cache] root`` from TOML wins."""
        monkeypatch.delenv(CACHE_ROOT_ENV_VAR, raising=False)
        explicit_root = tmp_path / "explicit"
        cfg = AppConfig(cache=CacheConfig(root=explicit_root))

        returned = bootstrap._prepare_cache_root(cfg, no_cache=False, clear_cache_first=False)
        assert returned == explicit_root


# ---------------------------------------------------------------------------
# create_check_command — writers + opt-in flag wiring
# ---------------------------------------------------------------------------


class TestCreateCheckCommandWiring:
    def test_writers_filenames_and_order(self) -> None:
        cmd = bootstrap.create_check_command()
        filenames = [name for name, _writer in cmd._writers]
        # RFC-0034: Slack writer is opt-in; default is 4 writers.
        assert filenames == [
            "freeze.md",
            "freeze.json",
            "freeze-inventory.csv",
            "freeze-findings.csv",
        ]

    def test_writers_count(self) -> None:
        cmd = bootstrap.create_check_command()
        # RFC-0034: 4 writers by default (Slack opt-in).
        assert len(cmd._writers) == 4

    def test_slack_flag_inserts_writer(self) -> None:
        cmd = bootstrap.create_check_command(slack=True)
        filenames = [name for name, _writer in cmd._writers]
        # Slack writer is inserted between json and the CSVs to match
        # the historical file-listing order when --slack is passed.
        assert filenames == [
            "freeze.md",
            "freeze.json",
            "freeze-slack.json",
            "freeze-inventory.csv",
            "freeze-findings.csv",
        ]

    def test_slack_config_inserts_writer(self) -> None:
        from gradle_deps_monitor.domain.config import AppConfig, OutputConfig

        cfg = AppConfig(output=OutputConfig(slack=True))
        cmd = bootstrap.create_check_command(app_config=cfg)
        filenames = [name for name, _writer in cmd._writers]
        assert "freeze-slack.json" in filenames

    def test_slack_flag_overrides_config(self) -> None:
        """CLI flag wins over config per RFC-0012 precedence."""
        from gradle_deps_monitor.domain.config import AppConfig, OutputConfig

        cfg = AppConfig(output=OutputConfig(slack=True))
        cmd = bootstrap.create_check_command(app_config=cfg, slack=False)
        filenames = [name for name, _writer in cmd._writers]
        assert "freeze-slack.json" not in filenames

    def test_module_usage_default_off_skips_scanner(self) -> None:
        cmd = bootstrap.create_check_command()
        assert cmd._use_case._module_usage_scanner is None

    def test_module_usage_true_wires_scanner(self) -> None:
        cmd = bootstrap.create_check_command(module_usage=True)
        assert cmd._use_case._module_usage_scanner is not None

    def test_risk_score_default_off(self) -> None:
        cmd = bootstrap.create_check_command()
        assert cmd._use_case._enable_risk_score is False

    def test_risk_score_true_enables(self) -> None:
        cmd = bootstrap.create_check_command(risk_score=True)
        assert cmd._use_case._enable_risk_score is True


# ---------------------------------------------------------------------------
# create_diff_command — writers + loader contract
# ---------------------------------------------------------------------------


class TestCreateDiffCommandWiring:
    def test_writers_filenames_and_order(self) -> None:
        cmd = bootstrap.create_diff_command()
        filenames = [name for name, _writer in cmd._writers]
        # RFC-0034: Slack writer is opt-in; default is 2 writers.
        assert filenames == [
            "freeze-diff.md",
            "freeze-diff.json",
        ]

    def test_writers_count(self) -> None:
        cmd = bootstrap.create_diff_command()
        # RFC-0034: 2 writers by default (Slack opt-in).
        assert len(cmd._writers) == 2

    def test_slack_flag_appends_writer(self) -> None:
        cmd = bootstrap.create_diff_command(slack=True)
        filenames = [name for name, _writer in cmd._writers]
        assert filenames == [
            "freeze-diff.md",
            "freeze-diff.json",
            "freeze-diff-slack.json",
        ]

    def test_slack_config_appends_writer(self) -> None:
        from gradle_deps_monitor.domain.config import AppConfig, OutputConfig

        cfg = AppConfig(output=OutputConfig(slack=True))
        cmd = bootstrap.create_diff_command(app_config=cfg)
        filenames = [name for name, _writer in cmd._writers]
        assert "freeze-diff-slack.json" in filenames

    def test_loader_is_json_snapshot_loader(self) -> None:
        cmd = bootstrap.create_diff_command()
        assert isinstance(cmd._loader, JsonSnapshotLoader)
