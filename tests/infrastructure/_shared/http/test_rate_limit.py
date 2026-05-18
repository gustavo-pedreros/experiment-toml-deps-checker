"""Unit tests for is_rate_limited (RFC-0030)."""

from __future__ import annotations

import httpx

from gradle_deps_monitor.infrastructure._shared.http import is_rate_limited


def _response(status: int, headers: dict[str, str] | None = None) -> httpx.Response:
    return httpx.Response(status, headers=headers or {})


class TestIsRateLimited:
    def test_429_is_rate_limit(self) -> None:
        assert is_rate_limited(_response(429)) is True

    def test_403_with_remaining_zero_is_rate_limit(self) -> None:
        assert is_rate_limited(_response(403, headers={"X-RateLimit-Remaining": "0"})) is True

    def test_403_without_header_is_not_rate_limit(self) -> None:
        assert is_rate_limited(_response(403)) is False

    def test_403_with_remaining_nonzero_is_not_rate_limit(self) -> None:
        assert is_rate_limited(_response(403, headers={"X-RateLimit-Remaining": "5"})) is False

    def test_200_is_not_rate_limit(self) -> None:
        assert is_rate_limited(_response(200)) is False

    def test_500_is_not_rate_limit(self) -> None:
        assert is_rate_limited(_response(500)) is False


class TestChangelogFetcherReexport:
    """``changelog_fetcher._is_rate_limited`` must alias the shared symbol."""

    def test_alias_is_shared_function(self) -> None:
        from gradle_deps_monitor.infrastructure.fetchers.changelog_fetcher import (
            _is_rate_limited,
        )

        assert _is_rate_limited is is_rate_limited
