"""Tests for RFC-0029 cache path / lifecycle helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from gradle_deps_monitor.domain.config import CacheConfig
from gradle_deps_monitor.infrastructure.cache.cache_paths import (
    CACHE_ROOT_ENV_VAR,
    clear_cache,
    default_cache_root,
    ephemeral_cache_root,
    resolve_cache_root,
)


class TestDefaultCacheRoot:
    def test_falls_back_to_home_when_env_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(CACHE_ROOT_ENV_VAR, raising=False)
        assert default_cache_root() == Path.home() / ".cache" / "gradle-deps-monitor"

    def test_honours_env_override(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv(CACHE_ROOT_ENV_VAR, str(tmp_path / "ci-cache"))
        assert default_cache_root() == tmp_path / "ci-cache"

    def test_treats_empty_env_value_as_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(CACHE_ROOT_ENV_VAR, "   ")
        assert default_cache_root() == Path.home() / ".cache" / "gradle-deps-monitor"

    def test_expands_user_in_env_value(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(CACHE_ROOT_ENV_VAR, "~/custom-cache")
        assert default_cache_root() == Path.home() / "custom-cache"


class TestResolveCacheRoot:
    def test_env_var_beats_config(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv(CACHE_ROOT_ENV_VAR, str(tmp_path / "env"))
        cfg = CacheConfig(root=tmp_path / "cfg")
        assert resolve_cache_root(cfg) == tmp_path / "env"

    def test_config_beats_default_when_env_unset(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.delenv(CACHE_ROOT_ENV_VAR, raising=False)
        cfg = CacheConfig(root=tmp_path / "cfg")
        assert resolve_cache_root(cfg) == tmp_path / "cfg"

    def test_default_when_neither_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(CACHE_ROOT_ENV_VAR, raising=False)
        cfg = CacheConfig()
        assert resolve_cache_root(cfg) == Path.home() / ".cache" / "gradle-deps-monitor"

    def test_expands_user_in_config_root(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(CACHE_ROOT_ENV_VAR, raising=False)
        cfg = CacheConfig(root=Path("~/custom-cache"))
        assert resolve_cache_root(cfg) == Path.home() / "custom-cache"


class TestClearCache:
    def test_removes_existing_tree(self, tmp_path: Path) -> None:
        root = tmp_path / "to-clear"
        (root / "sub").mkdir(parents=True)
        (root / "sub" / "leaf.txt").write_text("data")

        clear_cache(root)

        assert not root.exists()

    def test_silently_succeeds_when_root_absent(self, tmp_path: Path) -> None:
        clear_cache(tmp_path / "never-existed")  # no exception


class TestEphemeralCacheRoot:
    def test_returns_fresh_writable_directory(self) -> None:
        path = ephemeral_cache_root()
        try:
            assert path.is_dir()
            (path / "probe").write_text("ok")
            assert (path / "probe").read_text() == "ok"
        finally:
            clear_cache(path)

    def test_two_invocations_produce_distinct_paths(self) -> None:
        a = ephemeral_cache_root()
        b = ephemeral_cache_root()
        try:
            assert a != b
        finally:
            clear_cache(a)
            clear_cache(b)
