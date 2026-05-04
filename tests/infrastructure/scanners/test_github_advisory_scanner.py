"""Unit tests for GitHubAdvisoryScanner using httpx mock transport."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from gradle_deps_monitor.domain.advisory import AdvisorySeverity
from gradle_deps_monitor.domain.catalog import Library
from gradle_deps_monitor.domain.version import MavenVersion
from gradle_deps_monitor.infrastructure.scanners.github_advisory_scanner import (
    GitHubAdvisoryScanner,
    _evaluate_range,
    _version_in_range,
    _version_lt,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_OKHTTP_ADVISORY: dict = {
    "ghsa_id": "GHSA-xxxx-1234-yyyy",
    "cve_id": "CVE-2023-3635",
    "summary": "Information disclosure via header injection",
    "severity": "high",
    "html_url": "https://github.com/advisories/GHSA-xxxx-1234-yyyy",
    "vulnerabilities": [
        {
            "package": {"ecosystem": "maven", "name": "com.squareup.okhttp3:okhttp"},
            "vulnerable_version_range": "< 4.12.0",
            "first_patched_version": "4.12.0",
        }
    ],
}

_CRITICAL_ADVISORY: dict = {
    "ghsa_id": "GHSA-crit-0001-aaaa",
    "cve_id": "CVE-2023-9999",
    "summary": "Remote code execution",
    "severity": "critical",
    "html_url": "https://github.com/advisories/GHSA-crit-0001-aaaa",
    "vulnerabilities": [
        {
            "package": {"ecosystem": "maven", "name": "com.example:vuln-lib"},
            "vulnerable_version_range": ">= 1.0.0, < 2.0.0",
            "first_patched_version": "2.0.0",
        }
    ],
}

_MODERATE_ADVISORY: dict = {
    "ghsa_id": "GHSA-mod-0002-bbbb",
    "cve_id": None,
    "summary": "Moderate issue",
    "severity": "moderate",
    "html_url": "https://github.com/advisories/GHSA-mod-0002-bbbb",
    "vulnerabilities": [
        {
            "package": {"ecosystem": "maven", "name": "com.example:vuln-lib"},
            "vulnerable_version_range": ">= 1.0.0, < 2.0.0",
            "first_patched_version": "2.0.0",
        }
    ],
}


def _make_lib(alias: str, group: str, artifact: str, version: str) -> Library:
    return Library(alias=alias, group=group, artifact=artifact, version=MavenVersion(version))


def _mock_transport(responses: dict[str, list]) -> httpx.MockTransport:
    """Return a transport that replies with a JSON list for URLs matching the key."""

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url).split("?")[0]
        for pattern, data in responses.items():
            if pattern in url:
                return httpx.Response(200, json=data)
        return httpx.Response(200, json=[])

    return httpx.MockTransport(handler)


# ---------------------------------------------------------------------------
# Helpers — version comparison
# ---------------------------------------------------------------------------


class TestVersionLt:
    def test_simple(self) -> None:
        assert _version_lt("1.0.0", "2.0.0") is True
        assert _version_lt("2.0.0", "1.0.0") is False
        assert _version_lt("1.0.0", "1.0.0") is False

    def test_minor(self) -> None:
        assert _version_lt("1.9.0", "1.10.0") is True

    def test_patch(self) -> None:
        assert _version_lt("4.9.1", "4.12.0") is True

    def test_padded(self) -> None:
        assert _version_lt("1.0", "1.0.1") is True

    def test_pre_release_suffix_ignored(self) -> None:
        # Numeric prefix "1" < "2"
        assert _version_lt("1.9.22.Final", "2.0.0.Final") is True


class TestEvaluateRange:
    def test_less_than(self) -> None:
        assert _evaluate_range("4.9.1", "< 4.12.0") is True
        assert _evaluate_range("4.12.0", "< 4.12.0") is False
        assert _evaluate_range("5.0.0", "< 4.12.0") is False

    def test_gte_and_lt(self) -> None:
        assert _evaluate_range("1.5.0", ">= 1.0.0, < 2.0.0") is True
        assert _evaluate_range("0.9.0", ">= 1.0.0, < 2.0.0") is False
        assert _evaluate_range("2.0.0", ">= 1.0.0, < 2.0.0") is False

    def test_exact(self) -> None:
        assert _evaluate_range("1.2.3", "= 1.2.3") is True
        assert _evaluate_range("1.2.4", "= 1.2.3") is False


class TestVersionInRange:
    def test_fixed_version_determines_affected(self) -> None:
        assert _version_in_range("4.9.1", None, "4.12.0") is True
        assert _version_in_range("4.12.0", None, "4.12.0") is False

    def test_range_used_when_no_fixed(self) -> None:
        assert _version_in_range("1.5.0", ">= 1.0.0, < 2.0.0", None) is True
        assert _version_in_range("2.0.0", ">= 1.0.0, < 2.0.0", None) is False

    def test_conservative_when_no_info(self) -> None:
        # No fixed version, no range → surface conservatively
        assert _version_in_range("1.0.0", None, None) is True


# ---------------------------------------------------------------------------
# Scanner — API integration (mocked)
# ---------------------------------------------------------------------------


class TestGitHubAdvisoryScanner:
    @pytest.fixture()
    def tmp_cache(self, tmp_path: Path) -> Path:
        return tmp_path / "ghsa_cache"

    @pytest.mark.asyncio
    async def test_returns_advisory_for_affected_version(self, tmp_cache: Path) -> None:
        transport = _mock_transport({"advisories": [_OKHTTP_ADVISORY]})
        client = httpx.AsyncClient(transport=transport)
        scanner = GitHubAdvisoryScanner(cache_dir=tmp_cache, client=client)

        lib = _make_lib("okhttp", "com.squareup.okhttp3", "okhttp", "4.9.1")
        results = await scanner.scan((lib,))

        assert len(results) == 1
        la = results[0]
        assert la.alias == "okhttp"
        assert la.is_vulnerable is True
        assert la.advisories[0].severity == AdvisorySeverity.HIGH
        assert la.advisories[0].cve_id == "CVE-2023-3635"

    @pytest.mark.asyncio
    async def test_no_advisory_for_patched_version(self, tmp_cache: Path) -> None:
        transport = _mock_transport({"advisories": [_OKHTTP_ADVISORY]})
        client = httpx.AsyncClient(transport=transport)
        scanner = GitHubAdvisoryScanner(cache_dir=tmp_cache, client=client)

        lib = _make_lib("okhttp", "com.squareup.okhttp3", "okhttp", "4.12.0")
        results = await scanner.scan((lib,))

        assert results[0].is_vulnerable is False

    @pytest.mark.asyncio
    async def test_no_advisory_when_api_returns_empty(self, tmp_cache: Path) -> None:
        transport = _mock_transport({})
        client = httpx.AsyncClient(transport=transport)
        scanner = GitHubAdvisoryScanner(cache_dir=tmp_cache, client=client)

        lib = _make_lib("safe-lib", "com.example", "safe", "1.0.0")
        results = await scanner.scan((lib,))

        assert results[0].is_vulnerable is False

    @pytest.mark.asyncio
    async def test_maps_moderate_to_medium(self, tmp_cache: Path) -> None:
        transport = _mock_transport({"advisories": [_MODERATE_ADVISORY]})
        client = httpx.AsyncClient(transport=transport)
        scanner = GitHubAdvisoryScanner(cache_dir=tmp_cache, client=client)

        lib = _make_lib("vuln-lib", "com.example", "vuln-lib", "1.5.0")
        results = await scanner.scan((lib,))

        assert results[0].advisories[0].severity == AdvisorySeverity.MEDIUM

    @pytest.mark.asyncio
    async def test_maps_critical_severity(self, tmp_cache: Path) -> None:
        transport = _mock_transport({"advisories": [_CRITICAL_ADVISORY]})
        client = httpx.AsyncClient(transport=transport)
        scanner = GitHubAdvisoryScanner(cache_dir=tmp_cache, client=client)

        lib = _make_lib("vuln-lib", "com.example", "vuln-lib", "1.5.0")
        results = await scanner.scan((lib,))

        assert results[0].has_critical is True

    @pytest.mark.asyncio
    async def test_scans_multiple_libraries(self, tmp_cache: Path) -> None:
        transport = _mock_transport({"advisories": [_OKHTTP_ADVISORY]})
        client = httpx.AsyncClient(transport=transport)
        scanner = GitHubAdvisoryScanner(cache_dir=tmp_cache, client=client)

        libs = (
            _make_lib("okhttp", "com.squareup.okhttp3", "okhttp", "4.9.1"),
            _make_lib("retrofit", "com.squareup.retrofit2", "retrofit", "2.9.0"),
        )
        results = await scanner.scan(libs)

        assert len(results) == 2
        assert results[0].alias == "okhttp"
        assert results[1].alias == "retrofit"

    @pytest.mark.asyncio
    async def test_result_order_matches_input(self, tmp_cache: Path) -> None:
        transport = _mock_transport({})
        client = httpx.AsyncClient(transport=transport)
        scanner = GitHubAdvisoryScanner(cache_dir=tmp_cache, client=client)

        libs = tuple(_make_lib(f"lib-{i}", "com.example", f"lib-{i}", "1.0.0") for i in range(5))
        results = await scanner.scan(libs)

        assert [r.alias for r in results] == [lib.alias for lib in libs]

    @pytest.mark.asyncio
    async def test_uses_cache_on_second_call(self, tmp_cache: Path) -> None:
        call_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            return httpx.Response(200, json=[_OKHTTP_ADVISORY])

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        scanner = GitHubAdvisoryScanner(cache_dir=tmp_cache, client=client)

        lib = _make_lib("okhttp", "com.squareup.okhttp3", "okhttp", "4.9.1")
        await scanner.scan((lib,))
        await scanner.scan((lib,))

        assert call_count == 1  # second call used the cache

    @pytest.mark.asyncio
    async def test_advisory_ignores_different_package(self, tmp_cache: Path) -> None:
        """Advisory for package A should not appear for package B."""
        advisory_for_other = {
            **_OKHTTP_ADVISORY,
            "vulnerabilities": [
                {
                    "package": {"ecosystem": "maven", "name": "com.other:lib"},
                    "vulnerable_version_range": "< 99.0.0",
                    "first_patched_version": "99.0.0",
                }
            ],
        }
        transport = _mock_transport({"advisories": [advisory_for_other]})
        client = httpx.AsyncClient(transport=transport)
        scanner = GitHubAdvisoryScanner(cache_dir=tmp_cache, client=client)

        lib = _make_lib("okhttp", "com.squareup.okhttp3", "okhttp", "4.9.1")
        results = await scanner.scan((lib,))

        assert results[0].is_vulnerable is False
