"""Unit tests for OssIndexScanner using httpx mock transport."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from gradle_deps_monitor.application.ports.vulnerability_scanner import VulnerabilityScanError
from gradle_deps_monitor.domain.advisory import AdvisorySeverity
from gradle_deps_monitor.domain.catalog import Library
from gradle_deps_monitor.domain.version import MavenVersion
from gradle_deps_monitor.infrastructure.scanners.oss_index_scanner import (
    OssIndexScanner,
    _purl,
    _severity_from_cvss,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_OKHTTP_VULN: dict = {
    "id": "sonatype-2023-12345",
    "displayName": "CVE-2023-3635",
    "title": "Information disclosure via header injection",
    "description": "OkHttp allows header injection in certain configurations.",
    "cvssScore": 7.5,
    "cvssVector": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:N/A:N",
    "cve": "CVE-2023-3635",
    "cwe": "CWE-200",
    "reference": "https://ossindex.sonatype.org/vuln/sonatype-2023-12345",
    "externalReferences": [],
}

_CRITICAL_VULN: dict = {
    "id": "sonatype-2023-99999",
    "displayName": "CVE-2023-9999",
    "title": "Remote code execution",
    "description": "RCE via unsafe deserialization.",
    "cvssScore": 9.8,
    "cvssVector": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
    "cve": "CVE-2023-9999",
    "cwe": "CWE-502",
    "reference": "https://ossindex.sonatype.org/vuln/sonatype-2023-99999",
    "externalReferences": [],
}

_MEDIUM_VULN: dict = {
    "id": "sonatype-2023-55555",
    "displayName": "CVE-2023-5555",
    "title": "Moderate SSRF vulnerability",
    "description": "Server-side request forgery in certain configurations.",
    "cvssScore": 5.3,
    "cve": "CVE-2023-5555",
    "reference": "https://ossindex.sonatype.org/vuln/sonatype-2023-55555",
    "externalReferences": [],
}

_LOW_VULN: dict = {
    "id": "sonatype-2023-11111",
    "displayName": "CVE-2023-1111",
    "title": "Low severity information leak",
    "description": "Minimal impact advisory.",
    "cvssScore": 2.0,
    "cve": "CVE-2023-1111",
    "reference": "https://ossindex.sonatype.org/vuln/sonatype-2023-11111",
    "externalReferences": [],
}

_NO_CVE_VULN: dict = {
    "id": "sonatype-2023-77777",
    "displayName": "sonatype-2023-77777",
    "title": "Proprietary vulnerability without CVE",
    "description": "An issue tracked only by Sonatype.",
    "cvssScore": 6.1,
    "cve": "",
    "reference": "https://ossindex.sonatype.org/vuln/sonatype-2023-77777",
    "externalReferences": [],
}


def _make_lib(alias: str, group: str, artifact: str, version: str) -> Library:
    return Library(alias=alias, group=group, artifact=artifact, version=MavenVersion(version))


def _component_report(purl: str, vulns: list[dict]) -> dict:
    return {"coordinates": purl, "description": "", "reference": "", "vulnerabilities": vulns}


def _mock_transport(responses: dict[str, list[dict]]) -> httpx.MockTransport:
    """Return a transport that matches POST body coordinates to pre-canned responses."""

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        body = json.loads(request.content)
        components = []
        for purl in body.get("coordinates", []):
            vulns: list[dict] = []
            for pattern, vuln_list in responses.items():
                if pattern in purl:
                    vulns = vuln_list
                    break
            components.append(_component_report(purl, vulns))
        return httpx.Response(200, json=components)

    return httpx.MockTransport(handler)


# ---------------------------------------------------------------------------
# Helpers — PURL + CVSS
# ---------------------------------------------------------------------------


class TestPurl:
    def test_standard_maven_format(self) -> None:
        lib = _make_lib("okhttp", "com.squareup.okhttp3", "okhttp", "4.9.1")
        assert _purl(lib) == "pkg:maven/com.squareup.okhttp3/okhttp@4.9.1"

    def test_simple_group(self) -> None:
        lib = _make_lib("gson", "com.google.code.gson", "gson", "2.10.1")
        assert _purl(lib) == "pkg:maven/com.google.code.gson/gson@2.10.1"


class TestSeverityFromCvss:
    def test_critical(self) -> None:
        assert _severity_from_cvss(9.8) == AdvisorySeverity.CRITICAL
        assert _severity_from_cvss(9.0) == AdvisorySeverity.CRITICAL

    def test_high(self) -> None:
        assert _severity_from_cvss(7.5) == AdvisorySeverity.HIGH
        assert _severity_from_cvss(7.0) == AdvisorySeverity.HIGH

    def test_medium(self) -> None:
        assert _severity_from_cvss(5.3) == AdvisorySeverity.MEDIUM
        assert _severity_from_cvss(4.0) == AdvisorySeverity.MEDIUM

    def test_low(self) -> None:
        assert _severity_from_cvss(2.0) == AdvisorySeverity.LOW
        assert _severity_from_cvss(0.1) == AdvisorySeverity.LOW

    def test_unknown_when_none(self) -> None:
        assert _severity_from_cvss(None) == AdvisorySeverity.UNKNOWN

    def test_unknown_when_zero(self) -> None:
        assert _severity_from_cvss(0) == AdvisorySeverity.UNKNOWN


# ---------------------------------------------------------------------------
# Scanner — API integration (mocked)
# ---------------------------------------------------------------------------


class TestOssIndexScanner:
    @pytest.fixture()
    def tmp_cache(self, tmp_path: Path) -> Path:
        return tmp_path / "ossindex_cache"

    @pytest.mark.asyncio
    async def test_returns_advisory_for_vulnerable_component(self, tmp_cache: Path) -> None:
        transport = _mock_transport({"okhttp": [_OKHTTP_VULN]})
        client = httpx.AsyncClient(transport=transport)
        scanner = OssIndexScanner(cache_dir=tmp_cache, client=client)

        lib = _make_lib("okhttp", "com.squareup.okhttp3", "okhttp", "4.9.1")
        results = await scanner.scan((lib,))

        assert len(results) == 1
        la = results[0]
        assert la.alias == "okhttp"
        assert la.is_vulnerable is True
        assert la.advisories[0].cve_id == "CVE-2023-3635"
        assert la.advisories[0].severity == AdvisorySeverity.HIGH
        assert la.advisories[0].source == "oss_index"

    @pytest.mark.asyncio
    async def test_no_advisory_for_clean_component(self, tmp_cache: Path) -> None:
        transport = _mock_transport({})
        client = httpx.AsyncClient(transport=transport)
        scanner = OssIndexScanner(cache_dir=tmp_cache, client=client)

        lib = _make_lib("safe-lib", "com.example", "safe", "1.0.0")
        results = await scanner.scan((lib,))

        assert results[0].is_vulnerable is False

    @pytest.mark.asyncio
    async def test_maps_critical_cvss(self, tmp_cache: Path) -> None:
        transport = _mock_transport({"vuln-lib": [_CRITICAL_VULN]})
        client = httpx.AsyncClient(transport=transport)
        scanner = OssIndexScanner(cache_dir=tmp_cache, client=client)

        lib = _make_lib("vuln-lib", "com.example", "vuln-lib", "1.0.0")
        results = await scanner.scan((lib,))

        assert results[0].has_critical is True

    @pytest.mark.asyncio
    async def test_maps_medium_cvss(self, tmp_cache: Path) -> None:
        transport = _mock_transport({"some-lib": [_MEDIUM_VULN]})
        client = httpx.AsyncClient(transport=transport)
        scanner = OssIndexScanner(cache_dir=tmp_cache, client=client)

        lib = _make_lib("some-lib", "com.example", "some-lib", "1.0.0")
        results = await scanner.scan((lib,))

        assert results[0].advisories[0].severity == AdvisorySeverity.MEDIUM

    @pytest.mark.asyncio
    async def test_maps_low_cvss(self, tmp_cache: Path) -> None:
        transport = _mock_transport({"low-lib": [_LOW_VULN]})
        client = httpx.AsyncClient(transport=transport)
        scanner = OssIndexScanner(cache_dir=tmp_cache, client=client)

        lib = _make_lib("low-lib", "com.example", "low-lib", "1.0.0")
        results = await scanner.scan((lib,))

        assert results[0].advisories[0].severity == AdvisorySeverity.LOW

    @pytest.mark.asyncio
    async def test_advisory_without_cve_uses_oss_id(self, tmp_cache: Path) -> None:
        transport = _mock_transport({"some-lib": [_NO_CVE_VULN]})
        client = httpx.AsyncClient(transport=transport)
        scanner = OssIndexScanner(cache_dir=tmp_cache, client=client)

        lib = _make_lib("some-lib", "com.example", "some-lib", "1.0.0")
        results = await scanner.scan((lib,))

        adv = results[0].advisories[0]
        assert adv.cve_id is None
        assert adv.ghsa_id == "sonatype-2023-77777"

    @pytest.mark.asyncio
    async def test_fixed_version_is_none(self, tmp_cache: Path) -> None:
        """OSS Index does not return fixed versions."""
        transport = _mock_transport({"okhttp": [_OKHTTP_VULN]})
        client = httpx.AsyncClient(transport=transport)
        scanner = OssIndexScanner(cache_dir=tmp_cache, client=client)

        lib = _make_lib("okhttp", "com.squareup.okhttp3", "okhttp", "4.9.1")
        results = await scanner.scan((lib,))

        assert results[0].advisories[0].fixed_version is None

    @pytest.mark.asyncio
    async def test_result_order_matches_input(self, tmp_cache: Path) -> None:
        transport = _mock_transport({})
        client = httpx.AsyncClient(transport=transport)
        scanner = OssIndexScanner(cache_dir=tmp_cache, client=client)

        libs = tuple(_make_lib(f"lib-{i}", "com.example", f"lib-{i}", "1.0.0") for i in range(5))
        results = await scanner.scan(libs)

        assert [r.alias for r in results] == [lib.alias for lib in libs]

    @pytest.mark.asyncio
    async def test_uses_cache_on_second_call(self, tmp_cache: Path) -> None:
        call_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            return httpx.Response(
                200,
                json=[
                    _component_report(
                        "pkg:maven/com.squareup.okhttp3/okhttp@4.9.1",
                        [_OKHTTP_VULN],
                    )
                ],
            )

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        scanner = OssIndexScanner(cache_dir=tmp_cache, client=client)

        lib = _make_lib("okhttp", "com.squareup.okhttp3", "okhttp", "4.9.1")
        await scanner.scan((lib,))
        await scanner.scan((lib,))

        assert call_count == 1  # second call used the cache

    @pytest.mark.asyncio
    async def test_raises_on_api_error(self, tmp_cache: Path) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(429, json={"error": "rate limited"})

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        scanner = OssIndexScanner(cache_dir=tmp_cache, client=client)

        lib = _make_lib("lib", "com.example", "lib", "1.0.0")
        with pytest.raises(VulnerabilityScanError):
            await scanner.scan((lib,))

    @pytest.mark.asyncio
    async def test_batches_large_input(self, tmp_cache: Path) -> None:
        """More than _BATCH_SIZE libraries should be split into exactly 2 POST requests."""
        from gradle_deps_monitor.infrastructure.scanners.oss_index_scanner import _BATCH_SIZE

        request_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            import json

            nonlocal request_count
            request_count += 1
            body = json.loads(request.content)
            components = [_component_report(purl, []) for purl in body.get("coordinates", [])]
            return httpx.Response(200, json=components)

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        scanner = OssIndexScanner(cache_dir=tmp_cache, client=client)

        libs = tuple(
            _make_lib(f"lib-{i}", "com.example", f"lib-{i}", "1.0.0")
            for i in range(_BATCH_SIZE + 1)
        )
        await scanner.scan(libs)

        # _BATCH_SIZE + 1 PURLs → batch of 128 + batch of 1 = 2 POST requests.
        assert request_count == 2
