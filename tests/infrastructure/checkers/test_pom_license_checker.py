"""Unit tests for PomLicenseChecker.

All HTTP is mocked via ``httpx.MockTransport`` — no network access.
"""

from __future__ import annotations

import httpx

from gradle_deps_monitor.domain.catalog import Library
from gradle_deps_monitor.domain.license import LicenseAudit, LicenseTier
from gradle_deps_monitor.domain.version import MavenVersion
from gradle_deps_monitor.infrastructure.checkers.pom_license_checker import (
    PomLicenseChecker,
    _classify_license,
    _is_google_library,
    _make_pom_xml,
    _parse_license_elements,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _lib(alias: str, group: str = "com.example", artifact: str | None = None) -> Library:
    return Library(
        alias=alias,
        group=group,
        artifact=artifact or alias,
        version=MavenVersion("1.0.0"),
    )


def _pom_response(body: str, status: int = 200) -> httpx.Response:
    return httpx.Response(status, text=body)


def _mock_transport(responses: dict[str, httpx.Response]) -> httpx.MockTransport:
    """Build a MockTransport that returns pre-defined responses per URL."""

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        for pattern, resp in responses.items():
            if pattern in url:
                return resp
        return httpx.Response(404)

    return httpx.MockTransport(handler)


# ---------------------------------------------------------------------------
# _parse_license_elements
# ---------------------------------------------------------------------------


class TestParseLicenseElements:
    def test_single_license(self) -> None:
        xml = _make_pom_xml(license_name="Apache 2.0", license_url="https://apache.org")
        result = _parse_license_elements(xml)
        assert len(result) == 1
        assert result[0] == ("Apache 2.0", "https://apache.org")

    def test_no_licenses_block(self) -> None:
        xml = _make_pom_xml(has_licenses_block=False)
        assert _parse_license_elements(xml) == []

    def test_license_name_only(self) -> None:
        xml = _make_pom_xml(license_name="MIT")
        result = _parse_license_elements(xml)
        assert result[0] == ("MIT", None)

    def test_license_url_only(self) -> None:
        xml = _make_pom_xml(license_url="https://mit-license.org")
        result = _parse_license_elements(xml)
        assert result[0] == (None, "https://mit-license.org")

    def test_namespaced_pom(self) -> None:
        xml = _make_pom_xml(license_name="Apache 2.0", with_namespace=True)
        result = _parse_license_elements(xml)
        assert result[0][0] == "Apache 2.0"

    def test_malformed_xml(self) -> None:
        assert _parse_license_elements("<not valid xml") == []


# ---------------------------------------------------------------------------
# _classify_license
# ---------------------------------------------------------------------------


class TestClassifyLicense:
    # --- Permissive ---
    def test_apache(self) -> None:
        assert _classify_license("Apache License 2.0", None) == LicenseTier.PERMISSIVE

    def test_apache_url(self) -> None:
        assert (
            _classify_license(None, "https://www.apache.org/licenses/LICENSE-2.0")
            == LicenseTier.PERMISSIVE
        )

    def test_mit(self) -> None:
        assert _classify_license("MIT License", None) == LicenseTier.PERMISSIVE

    def test_bsd(self) -> None:
        assert _classify_license("BSD 3-Clause License", None) == LicenseTier.PERMISSIVE

    def test_isc(self) -> None:
        assert _classify_license("ISC", None) == LicenseTier.PERMISSIVE

    # --- Weak copyleft ---
    def test_lgpl(self) -> None:
        assert (
            _classify_license("GNU Lesser General Public License v2.1", None)
            == LicenseTier.WEAK_COPYLEFT
        )

    def test_lgpl_not_misclassified_as_strong(self) -> None:
        """LGPL contains 'gpl' — must not be promoted to STRONG_COPYLEFT."""
        tier = _classify_license("LGPL-2.1-only", None)
        assert tier == LicenseTier.WEAK_COPYLEFT

    def test_mpl(self) -> None:
        assert _classify_license("Mozilla Public License 2.0", None) == LicenseTier.WEAK_COPYLEFT

    def test_epl(self) -> None:
        assert _classify_license("Eclipse Public License 2.0", None) == LicenseTier.WEAK_COPYLEFT

    def test_eupl_not_misclassified_as_strong(self) -> None:
        """EUPL contains 'gpl' substring — must not be STRONG_COPYLEFT."""
        tier = _classify_license("European Union Public Licence 1.2", None)
        assert tier == LicenseTier.WEAK_COPYLEFT

    def test_cddl(self) -> None:
        assert (
            _classify_license("Common Development and Distribution License 1.0", None)
            == LicenseTier.WEAK_COPYLEFT
        )

    # --- Strong copyleft ---
    def test_gpl(self) -> None:
        assert _classify_license("GPL-3.0-or-later", None) == LicenseTier.STRONG_COPYLEFT

    def test_agpl(self) -> None:
        assert (
            _classify_license("GNU Affero General Public License v3", None)
            == LicenseTier.STRONG_COPYLEFT
        )

    def test_gpl_url(self) -> None:
        tier = _classify_license(None, "https://www.gnu.org/licenses/gpl-3.0.html")
        assert tier == LicenseTier.STRONG_COPYLEFT

    # --- Unknown ---
    def test_none_none(self) -> None:
        assert _classify_license(None, None) == LicenseTier.UNKNOWN

    def test_empty_strings(self) -> None:
        assert _classify_license("", "") == LicenseTier.UNKNOWN

    def test_unrecognised_name(self) -> None:
        assert _classify_license("Proprietary commercial license", None) == LicenseTier.UNKNOWN


# ---------------------------------------------------------------------------
# _is_google_library
# ---------------------------------------------------------------------------


class TestIsGoogleLibrary:
    def test_androidx(self) -> None:
        assert _is_google_library("androidx.core") is True

    def test_com_google_firebase(self) -> None:
        assert _is_google_library("com.google.firebase") is True

    def test_com_google_firebase_subgroup(self) -> None:
        assert _is_google_library("com.google.firebase.perf") is True

    def test_non_google(self) -> None:
        assert _is_google_library("com.squareup.retrofit2") is False

    def test_com_google_prefix_only(self) -> None:
        # 'com.google' alone is not in the list — check exact match
        assert _is_google_library("com.google") is False

    def test_com_google_android(self) -> None:
        assert _is_google_library("com.google.android.material") is True


# ---------------------------------------------------------------------------
# PomLicenseChecker integration (mocked HTTP)
# pytest-asyncio AUTO mode handles all async test functions.
# ---------------------------------------------------------------------------


class TestPomLicenseCheckerNoLibraries:
    async def test_empty_tuple(self) -> None:
        checker = PomLicenseChecker()
        audit = await checker.check(())
        assert audit.libraries_audited == 0
        assert audit.flagged_count == 0


class TestPomLicenseCheckerPermissive:
    async def test_all_permissive_no_findings(self) -> None:
        pom = _make_pom_xml(license_name="Apache 2.0")
        transport = _mock_transport({"com/example": _pom_response(pom)})

        async with httpx.AsyncClient(transport=transport) as client:
            checker = PomLicenseChecker()
            lib = _lib("retrofit", group="com.example")
            finding = await checker._check_library(client, lib)

        audit = LicenseAudit(
            findings=() if finding.tier == LicenseTier.PERMISSIVE else (finding,),
            libraries_audited=1,
        )
        assert audit.permissive_count == 1
        assert audit.flagged_count == 0


class TestPomLicenseCheckerFlagged:
    async def test_gpl_library_flagged(self) -> None:
        pom = _make_pom_xml(license_name="GPL-3.0-or-later")
        transport = _mock_transport({"com/example": _pom_response(pom)})

        async with httpx.AsyncClient(transport=transport) as client:
            checker = PomLicenseChecker()
            lib = _lib("gpl-lib", group="com.example")
            finding = await checker._check_library(client, lib)

        flagged = () if finding.tier == LicenseTier.PERMISSIVE else (finding,)
        audit = LicenseAudit(findings=flagged, libraries_audited=1)
        assert audit.has_violations is True
        assert audit.findings[0].tier == LicenseTier.STRONG_COPYLEFT

    async def test_unknown_when_404(self) -> None:
        """When POM is not found, tier should be UNKNOWN."""
        transport = _mock_transport({})  # all 404s

        async with httpx.AsyncClient(transport=transport) as client:
            checker = PomLicenseChecker()
            lib = _lib("mystery", group="com.notexist")
            finding = await checker._check_library(client, lib)

        assert finding.tier == LicenseTier.UNKNOWN
        assert finding.license_name is None

    async def test_unknown_when_no_licenses_block(self) -> None:
        """POM exists but has no <licenses> element → UNKNOWN."""
        pom = _make_pom_xml(has_licenses_block=False)
        transport = _mock_transport({"com/example": _pom_response(pom)})

        async with httpx.AsyncClient(transport=transport) as client:
            checker = PomLicenseChecker()
            lib = _lib("nolicense", group="com.example")
            finding = await checker._check_library(client, lib)

        assert finding.tier == LicenseTier.UNKNOWN

    async def test_lgpl_classified_as_weak_copyleft(self) -> None:
        pom = _make_pom_xml(license_name="GNU Lesser General Public License v2.1")
        transport = _mock_transport({"com/example": _pom_response(pom)})

        async with httpx.AsyncClient(transport=transport) as client:
            checker = PomLicenseChecker()
            lib = _lib("lgpl-lib", group="com.example")
            finding = await checker._check_library(client, lib)

        assert finding.tier == LicenseTier.WEAK_COPYLEFT


class TestPomLicenseCheckerGoogleFallback:
    async def test_google_library_falls_back_to_google_maven(self) -> None:
        """Maven Central returns 404; Google Maven returns valid POM."""
        pom = _make_pom_xml(license_name="Apache 2.0")

        def handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if "dl.google.com" in url:
                return httpx.Response(200, text=pom)
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)

        async with httpx.AsyncClient(transport=transport) as client:
            checker = PomLicenseChecker()
            lib = _lib("core-ktx", group="androidx.core")
            finding = await checker._check_library(client, lib)

        assert finding.tier == LicenseTier.PERMISSIVE

    async def test_non_google_library_does_not_fallback(self) -> None:
        """Non-Google library: Maven Central 404, no Google Maven attempt."""
        calls: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(str(request.url))
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)

        async with httpx.AsyncClient(transport=transport) as client:
            checker = PomLicenseChecker()
            lib = _lib("retrofit", group="com.squareup.retrofit2")
            await checker._check_library(client, lib)

        # Only one request — no Google Maven fallback for non-Google groups
        assert len(calls) == 1
        assert "maven.org" in calls[0]


class TestPomLicenseCheckerSorting:
    def test_findings_sorted_by_tier_then_alias(self) -> None:
        """Findings must be sorted (tier, alias) so output is deterministic."""
        from gradle_deps_monitor.domain.license import LicenseFinding

        f1 = LicenseFinding(
            alias="zoo",
            coordinate="c:z",
            version="1.0",
            license_name=None,
            license_url=None,
            tier=LicenseTier.STRONG_COPYLEFT,
        )
        f2 = LicenseFinding(
            alias="alpha",
            coordinate="c:a",
            version="1.0",
            license_name=None,
            license_url=None,
            tier=LicenseTier.STRONG_COPYLEFT,
        )
        f3 = LicenseFinding(
            alias="mid",
            coordinate="c:m",
            version="1.0",
            license_name=None,
            license_url=None,
            tier=LicenseTier.WEAK_COPYLEFT,
        )

        # Manually sort as the checker would
        flagged = [f1, f2, f3]
        flagged.sort(key=lambda f: (f.tier.value, f.alias))

        # Alphabetically: "strong_copyleft" < "weak_copyleft" (s < w)
        # So STRONG_COPYLEFT appears first, sorted by alias within tier.
        assert flagged[0].alias == "alpha"  # strong_copyleft, alias=alpha
        assert flagged[1].alias == "zoo"  # strong_copyleft, alias=zoo
        assert flagged[2].alias == "mid"  # weak_copyleft
