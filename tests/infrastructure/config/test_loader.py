"""Unit tests for the TOML config loader (RFC-0012)."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from gradle_deps_monitor.domain.config import AppConfig, CacheConfig
from gradle_deps_monitor.domain.risk_score import RiskThresholds, RiskWeights
from gradle_deps_monitor.infrastructure.config.loader import (
    CONFIG_FILENAME,
    ConfigError,
    load_config,
)


def _write(tmp_path: Path, content: str) -> Path:
    path = tmp_path / CONFIG_FILENAME
    path.write_text(content, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Missing file → defaults
# ---------------------------------------------------------------------------


class TestMissingFile:
    def test_returns_defaults(self, tmp_path: Path) -> None:
        cfg = load_config(tmp_path)
        assert cfg == AppConfig()
        assert cfg.risk_weights == RiskWeights()
        assert cfg.risk_thresholds == RiskThresholds()


# ---------------------------------------------------------------------------
# Valid configurations
# ---------------------------------------------------------------------------


class TestRiskWeights:
    def test_full_section(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            """
[risk_weights]
outdatedness = 20
cve          = 40
abandonment  = 15
blast_radius = 10
compliance   = 10
license      = 5
""",
        )
        cfg = load_config(tmp_path)
        assert cfg.risk_weights.cve == 40
        assert cfg.risk_weights.outdatedness == 20
        assert cfg.risk_weights.license == 5

    def test_partial_overrides_keep_defaults(self, tmp_path: Path) -> None:
        # Override only `cve`. To keep the sum at 100, we also reduce
        # one other dimension. Defaults: out=25, cve=30, ab=15, br=15,
        # comp=10, lic=5. Bumping cve to 35 means we must drop something
        # by 5 — drop outdatedness to 20.
        _write(
            tmp_path,
            """
[risk_weights]
cve          = 35
outdatedness = 20
""",
        )
        cfg = load_config(tmp_path)
        assert cfg.risk_weights.cve == 35
        assert cfg.risk_weights.outdatedness == 20
        # Untouched dimensions keep defaults
        assert cfg.risk_weights.abandonment == 15
        assert cfg.risk_weights.blast_radius == 15

    def test_invalid_sum_raises(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path,
            """
[risk_weights]
cve = 99
""",
        )
        with pytest.raises(ConfigError, match="Invalid \\[risk_weights\\]"):
            load_config(tmp_path)
        # Error message includes the path so users can find the file.
        with pytest.raises(ConfigError, match=str(path)):
            load_config(tmp_path)

    def test_non_integer_value_rejected(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            """
[risk_weights]
cve = "high"
""",
        )
        with pytest.raises(ConfigError, match="must be an integer"):
            load_config(tmp_path)

    def test_boolean_value_rejected(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            """
[risk_weights]
cve = true
""",
        )
        with pytest.raises(ConfigError, match="must be an integer"):
            load_config(tmp_path)

    def test_unknown_key_warned_but_kept_loading(
        self,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        _write(
            tmp_path,
            """
[risk_weights]
cve              = 30
mystery_factor   = 99
""",
        )
        with caplog.at_level(logging.WARNING):
            cfg = load_config(tmp_path)
        assert cfg.risk_weights.cve == 30
        assert "mystery_factor" in caplog.text


class TestRiskThresholds:
    def test_full_section(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            """
[risk_thresholds]
critical = 80
high     = 60
medium   = 40
""",
        )
        cfg = load_config(tmp_path)
        assert cfg.risk_thresholds.critical == 80
        assert cfg.risk_thresholds.high == 60
        assert cfg.risk_thresholds.medium == 40

    def test_partial_keeps_defaults(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            """
[risk_thresholds]
critical = 90
""",
        )
        cfg = load_config(tmp_path)
        assert cfg.risk_thresholds.critical == 90
        # Default high=50, medium=30 still hold
        assert cfg.risk_thresholds.high == 50
        assert cfg.risk_thresholds.medium == 30

    def test_invalid_order_raises(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            """
[risk_thresholds]
critical = 30
high     = 50
medium   = 70
""",
        )
        with pytest.raises(ConfigError, match="Invalid \\[risk_thresholds\\]"):
            load_config(tmp_path)


# ---------------------------------------------------------------------------
# Mixed and edge cases
# ---------------------------------------------------------------------------


class TestMixedSections:
    def test_both_sections_set(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            """
[risk_weights]
cve          = 35
outdatedness = 20

[risk_thresholds]
critical = 90
high     = 70
medium   = 40
""",
        )
        cfg = load_config(tmp_path)
        assert cfg.risk_weights.cve == 35
        assert cfg.risk_thresholds.critical == 90

    def test_unknown_top_level_section_warned(
        self,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        _write(
            tmp_path,
            """
[risk_weights]
cve          = 35
outdatedness = 20

[unknown_section]
foo = "bar"
""",
        )
        with caplog.at_level(logging.WARNING):
            cfg = load_config(tmp_path)
        assert cfg.risk_weights.cve == 35
        assert "unknown_section" in caplog.text

    def test_reserved_sections_do_not_warn(
        self,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """``[output]`` and ``[library_health]`` are reserved for future RFCs.

        ``[cache]`` is no longer "reserved-but-unused"; it is wired in
        RFC-0029 and has its own dedicated tests below.
        """
        _write(
            tmp_path,
            """
[output]
default_dir = "freeze-reports"

[library_health]
extra_kb_path = "ops/extra.yaml"
""",
        )
        with caplog.at_level(logging.WARNING):
            cfg = load_config(tmp_path)
        # Risk weights and risk thresholds use defaults; cache also uses defaults.
        assert cfg == AppConfig()
        assert "output" not in caplog.text.lower() or "ignored" not in caplog.text.lower()
        assert "library_health" not in caplog.text.lower() or "ignored" not in caplog.text.lower()


# ---------------------------------------------------------------------------
# Malformed input
# ---------------------------------------------------------------------------


class TestMalformedInput:
    def test_invalid_toml_raises_with_path(self, tmp_path: Path) -> None:
        path = _write(tmp_path, "not = valid = toml")
        with pytest.raises(ConfigError, match="Invalid TOML"):
            load_config(tmp_path)
        with pytest.raises(ConfigError, match=str(path)):
            load_config(tmp_path)

    def test_section_must_be_table(self, tmp_path: Path) -> None:
        _write(tmp_path, 'risk_weights = "oops"')
        with pytest.raises(ConfigError, match="must be a TOML table"):
            load_config(tmp_path)

    def test_empty_file_returns_defaults(self, tmp_path: Path) -> None:
        _write(tmp_path, "")
        assert load_config(tmp_path) == AppConfig()


# ---------------------------------------------------------------------------
# [cache] section (RFC-0029)
# ---------------------------------------------------------------------------


class TestCacheSection:
    def test_missing_section_uses_defaults(self, tmp_path: Path) -> None:
        _write(tmp_path, "")
        cfg = load_config(tmp_path)
        assert cfg.cache == CacheConfig()

    def test_full_section_parsed(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            """
[cache]
root = "/var/cache/gradle-deps-monitor"
ttl_seconds_maven = 7200
ttl_seconds_advisory = 3600
""",
        )
        cfg = load_config(tmp_path)
        assert cfg.cache.root == Path("/var/cache/gradle-deps-monitor")
        assert cfg.cache.ttl_seconds_maven == 7200
        assert cfg.cache.ttl_seconds_advisory == 3600

    def test_partial_section_preserves_other_defaults(self, tmp_path: Path) -> None:
        _write(tmp_path, "[cache]\nttl_seconds_advisory = 600\n")
        cfg = load_config(tmp_path)
        defaults = CacheConfig()
        assert cfg.cache.root is None
        assert cfg.cache.ttl_seconds_maven == defaults.ttl_seconds_maven
        assert cfg.cache.ttl_seconds_advisory == 600

    def test_unknown_keys_warn(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        _write(tmp_path, "[cache]\nttl_seconds = 60\n")  # typo: no _maven / _advisory
        with caplog.at_level(logging.WARNING):
            load_config(tmp_path)
        assert "ttl_seconds" in caplog.text
        assert "ignored" in caplog.text

    def test_section_must_be_table(self, tmp_path: Path) -> None:
        _write(tmp_path, 'cache = "oops"')
        with pytest.raises(ConfigError, match=r"\[cache\].*must be a TOML table"):
            load_config(tmp_path)

    def test_root_must_be_non_empty_string(self, tmp_path: Path) -> None:
        _write(tmp_path, '[cache]\nroot = ""\n')
        with pytest.raises(ConfigError, match="non-empty string"):
            load_config(tmp_path)

    def test_root_rejects_non_string(self, tmp_path: Path) -> None:
        _write(tmp_path, "[cache]\nroot = 42\n")
        with pytest.raises(ConfigError, match="non-empty string"):
            load_config(tmp_path)

    def test_ttl_must_be_integer(self, tmp_path: Path) -> None:
        _write(tmp_path, "[cache]\nttl_seconds_maven = true\n")
        with pytest.raises(ConfigError, match="must be an integer"):
            load_config(tmp_path)

    def test_negative_ttl_rejected(self, tmp_path: Path) -> None:
        _write(tmp_path, "[cache]\nttl_seconds_maven = -1\n")
        with pytest.raises(ConfigError, match="must be >= 0"):
            load_config(tmp_path)

    def test_root_with_tilde_is_expanded(self, tmp_path: Path) -> None:
        _write(tmp_path, '[cache]\nroot = "~/.custom-cache"\n')
        cfg = load_config(tmp_path)
        assert cfg.cache.root == Path.home() / ".custom-cache"
