"""Unit tests for HttpPolicy validation (RFC-0030)."""

from __future__ import annotations

import pytest

from gradle_deps_monitor.infrastructure._shared.http import HttpPolicy


class TestHttpPolicyDefaults:
    def test_defaults_are_valid(self) -> None:
        policy = HttpPolicy()
        assert policy.timeout_seconds == 30.0
        assert policy.max_attempts == 3
        assert policy.max_concurrency == 20


class TestHttpPolicyValidation:
    def test_zero_timeout_rejected(self) -> None:
        with pytest.raises(ValueError, match="timeout_seconds must be > 0"):
            HttpPolicy(timeout_seconds=0)

    def test_negative_timeout_rejected(self) -> None:
        with pytest.raises(ValueError, match="timeout_seconds must be > 0"):
            HttpPolicy(timeout_seconds=-1.0)

    def test_zero_attempts_rejected(self) -> None:
        with pytest.raises(ValueError, match="max_attempts must be >= 1"):
            HttpPolicy(max_attempts=0)

    def test_negative_backoff_base_rejected(self) -> None:
        with pytest.raises(ValueError, match="backoff_base_seconds must be >= 0"):
            HttpPolicy(backoff_base_seconds=-0.5)

    def test_backoff_max_below_base_rejected(self) -> None:
        with pytest.raises(ValueError, match=">= backoff_base_seconds"):
            HttpPolicy(backoff_base_seconds=10.0, backoff_max_seconds=5.0)

    def test_zero_concurrency_rejected(self) -> None:
        with pytest.raises(ValueError, match="max_concurrency must be >= 1"):
            HttpPolicy(max_concurrency=0)
