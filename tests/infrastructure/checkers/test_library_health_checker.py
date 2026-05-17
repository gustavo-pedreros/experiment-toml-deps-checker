"""Unit tests for LibraryHealthChecker.

All HTTP calls are intercepted with httpx.MockTransport so no network
traffic is required.
"""

from __future__ import annotations

import asyncio
from datetime import date
from typing import Any
from unittest.mock import patch

import httpx

from gradle_deps_monitor.domain.catalog import Library
from gradle_deps_monitor.domain.library_health import HealthSignal, LibraryHealthSeverity
from gradle_deps_monitor.domain.version import MavenVersion
from gradle_deps_monitor.infrastructure.checkers.library_health_checker import (
    LibraryHealthChecker,
    _is_google_library,
    _is_stable_by_design,
    _parse_last_updated,
    _parse_relocation,
)

# ---------------------------------------------------------------------------
# Reference date — fixed so tests are deterministic.
# ---------------------------------------------------------------------------
_TODAY = date(2026, 5, 4)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _lib(alias: str, group: str, artifact: str, version: str = "1.0.0") -> Library:
    return Library(alias=alias, group=group, artifact=artifact, version=MavenVersion(version))


def _run(coro: Any) -> Any:
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# _is_google_library
# ---------------------------------------------------------------------------


class TestIsGoogleLibrary:
    def test_androidx(self) -> None:
        assert _is_google_library("androidx.core") is True

    def test_androidx_exact(self) -> None:
        assert _is_google_library("androidx") is True

    def test_com_google_android(self) -> None:
        assert _is_google_library("com.google.android.material") is True

    def test_com_google_firebase(self) -> None:
        assert _is_google_library("com.google.firebase") is True

    def test_com_android(self) -> None:
        assert _is_google_library("com.android.tools") is True

    def test_non_google(self) -> None:
        assert _is_google_library("com.squareup.okhttp3") is False

    def test_prefix_not_included(self) -> None:
        # "com.androidmock" should NOT match "com.android"
        assert _is_google_library("com.androidmock") is False


# ---------------------------------------------------------------------------
# _is_stable_by_design (issue #10 from the 2026-05 stress test menu)
# ---------------------------------------------------------------------------


class TestIsStableByDesign:
    def test_javax_inject(self) -> None:
        """``javax.inject:javax.inject`` is the JSR-330 reference impl —
        frozen by design, must not trigger the inactivity heuristic."""
        assert _is_stable_by_design("javax.inject") is True

    def test_javax_exact(self) -> None:
        assert _is_stable_by_design("javax") is True

    def test_jakarta_inject(self) -> None:
        """The Jakarta EE namespace succeeded ``javax`` for the same kinds
        of frozen spec libraries; treat both identically."""
        assert _is_stable_by_design("jakarta.inject") is True

    def test_non_spec_library(self) -> None:
        assert _is_stable_by_design("com.squareup.retrofit2") is False

    def test_prefix_not_overmatched(self) -> None:
        """``javaxmock`` shouldn't trip the ``javax`` prefix — must be
        either exact or followed by a dot."""
        assert _is_stable_by_design("javaxmock") is False


# ---------------------------------------------------------------------------
# _parse_relocation
# ---------------------------------------------------------------------------


class TestParseRelocation:
    def test_no_relocation(self) -> None:
        pom = """<project>
  <groupId>com.example</groupId>
  <artifactId>my-lib</artifactId>
  <version>1.0.0</version>
</project>"""
        assert _parse_relocation(pom) is None

    def test_with_relocation(self) -> None:
        pom = """<project>
  <distributionManagement>
    <relocation>
      <groupId>com.new</groupId>
      <artifactId>new-artifact</artifactId>
      <message>Moved to new coordinates.</message>
    </relocation>
  </distributionManagement>
</project>"""
        result = _parse_relocation(pom)
        assert result is not None
        assert result["groupId"] == "com.new"
        assert result["artifactId"] == "new-artifact"
        assert result["message"] == "Moved to new coordinates."

    def test_relocation_with_namespace(self) -> None:
        pom = """<project xmlns="http://maven.apache.org/POM/4.0.0">
  <distributionManagement>
    <relocation>
      <groupId>com.new</groupId>
    </relocation>
  </distributionManagement>
</project>"""
        result = _parse_relocation(pom)
        assert result is not None
        assert result["groupId"] == "com.new"

    def test_relocation_only_group(self) -> None:
        pom = """<project>
  <distributionManagement>
    <relocation>
      <groupId>com.new</groupId>
    </relocation>
  </distributionManagement>
</project>"""
        result = _parse_relocation(pom)
        assert result == {"groupId": "com.new"}

    def test_invalid_xml(self) -> None:
        assert _parse_relocation("<not valid xml") is None

    def test_no_distribution_management(self) -> None:
        pom = "<project><groupId>foo</groupId></project>"
        assert _parse_relocation(pom) is None


# ---------------------------------------------------------------------------
# _parse_last_updated
# ---------------------------------------------------------------------------


class TestParseLastUpdated:
    def test_valid(self) -> None:
        metadata = """<metadata>
  <versioning>
    <lastUpdated>20220101120000</lastUpdated>
  </versioning>
</metadata>"""
        result = _parse_last_updated(metadata)
        assert result == date(2022, 1, 1)

    def test_with_namespace(self) -> None:
        metadata = """<metadata xmlns="http://maven.apache.org/metadata">
  <versioning>
    <lastUpdated>20230615000000</lastUpdated>
  </versioning>
</metadata>"""
        result = _parse_last_updated(metadata)
        assert result == date(2023, 6, 15)

    def test_invalid_xml(self) -> None:
        assert _parse_last_updated("<bad xml") is None

    def test_missing_versioning(self) -> None:
        assert _parse_last_updated("<metadata></metadata>") is None

    def test_missing_last_updated(self) -> None:
        metadata = "<metadata><versioning></versioning></metadata>"
        assert _parse_last_updated(metadata) is None

    def test_short_value(self) -> None:
        metadata = "<metadata><versioning><lastUpdated>202201</lastUpdated></versioning></metadata>"
        assert _parse_last_updated(metadata) is None


# ---------------------------------------------------------------------------
# LibraryHealthChecker — curated KB
# ---------------------------------------------------------------------------


class TestCuratedKb:
    def _checker(self) -> LibraryHealthChecker:
        return LibraryHealthChecker(reference_date=_TODAY)

    def test_butterknife_detected(self) -> None:
        checker = self._checker()
        lib = _lib("butterknife", "com.jakewharton", "butterknife")
        findings = _run(checker.check((lib,)))
        assert len(findings) == 1
        f = findings[0]
        assert f.alias == "butterknife"
        assert f.signal == HealthSignal.CURATED
        assert f.severity == LibraryHealthSeverity.HIGH
        assert f.replacement is not None

    def test_rxjava1_high_severity(self) -> None:
        checker = self._checker()
        lib = _lib("rxjava", "io.reactivex", "rxjava")
        findings = _run(checker.check((lib,)))
        assert len(findings) == 1
        assert findings[0].severity == LibraryHealthSeverity.HIGH

    def test_rxjava2_medium_severity(self) -> None:
        checker = self._checker()
        lib = _lib("rxjava2", "io.reactivex.rxjava2", "rxjava")
        findings = _run(checker.check((lib,)))
        assert len(findings) == 1
        assert findings[0].severity == LibraryHealthSeverity.MEDIUM

    def test_migration_url_present(self) -> None:
        checker = self._checker()
        lib = _lib("butterknife", "com.jakewharton", "butterknife")
        findings = _run(checker.check((lib,)))
        assert findings[0].migration_url is not None

    def test_support_library_detected(self) -> None:
        checker = self._checker()
        lib = _lib("appcompat-v7", "com.android.support", "appcompat-v7")
        findings = _run(checker.check((lib,)))
        assert len(findings) == 1
        assert findings[0].signal == HealthSignal.CURATED

    def test_unknown_library_not_in_kb(self) -> None:
        """Library not in the KB should not produce a curated finding."""
        checker = self._checker()
        lib = _lib("okhttp", "com.squareup.okhttp3", "okhttp")
        # We patch out HTTP so the test is fast
        with patch.object(checker, "_run_http_checks", return_value=[]):
            findings = _run(checker.check((lib,)))
        assert not any(f.signal == HealthSignal.CURATED for f in findings)

    def test_curated_library_skips_http(self) -> None:
        """Libraries matched by curated KB must not trigger HTTP checks."""
        checker = self._checker()
        lib = _lib("butterknife", "com.jakewharton", "butterknife")
        with patch.object(checker, "_run_http_checks") as mock_http:
            _run(checker.check((lib,)))
        mock_http.assert_not_called()

    def test_empty_libraries(self) -> None:
        checker = self._checker()
        findings = _run(checker.check(()))
        assert findings == ()


# ---------------------------------------------------------------------------
# LibraryHealthChecker — POM relocation (mocked HTTP)
# ---------------------------------------------------------------------------

_RELOCATION_POM = """<project>
  <distributionManagement>
    <relocation>
      <groupId>com.new</groupId>
      <artifactId>new-artifact</artifactId>
      <message>Relocated.</message>
    </relocation>
  </distributionManagement>
</project>"""

_EMPTY_POM = "<project><groupId>com.example</groupId></project>"

_INACTIVE_METADATA = """<metadata>
  <versioning>
    <lastUpdated>20200101000000</lastUpdated>
  </versioning>
</metadata>"""

_RECENT_METADATA = """<metadata>
  <versioning>
    <lastUpdated>20260101000000</lastUpdated>
  </versioning>
</metadata>"""


def _mock_transport(responses: dict[str, tuple[int, str]]) -> httpx.MockTransport:
    """Return a MockTransport that returns canned responses keyed by URL."""

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        for pattern, (status, body) in responses.items():
            if pattern in url:
                return httpx.Response(status, text=body)
        return httpx.Response(404, text="not found")

    return httpx.MockTransport(handler)


class TestPomRelocation:
    def _checker(self) -> LibraryHealthChecker:
        return LibraryHealthChecker(reference_date=_TODAY)

    def _run_with_transport(
        self, checker: LibraryHealthChecker, libraries: tuple[Library, ...], transport: Any
    ) -> tuple:
        """Patch the httpx.AsyncClient transport to use our mock."""

        async def _inner() -> tuple:
            async with httpx.AsyncClient(transport=transport, timeout=15.0) as client:
                results = await checker._run_http_checks(client, list(libraries))
            return tuple(results)

        return asyncio.get_event_loop().run_until_complete(_inner())

    def test_relocation_finding(self) -> None:
        checker = self._checker()
        lib = _lib("old-lib", "com.old", "old-artifact", "1.0.0")
        transport = _mock_transport(
            {
                "old-artifact-1.0.0.pom": (200, _RELOCATION_POM),
            }
        )
        findings = self._run_with_transport(checker, (lib,), transport)
        assert len(findings) == 1
        f = findings[0]
        assert f.signal == HealthSignal.RELOCATED
        assert f.severity == LibraryHealthSeverity.HIGH
        assert f.replacement == "com.new:new-artifact"
        assert "Relocated." in f.message

    def test_relocation_skips_inactivity(self) -> None:
        """When relocation is found, inactivity check must not run."""
        checker = self._checker()
        lib = _lib("old-lib", "com.old", "old-artifact", "1.0.0")
        # Only POM responds — metadata would 404; no inactivity finding expected.
        transport = _mock_transport(
            {
                "old-artifact-1.0.0.pom": (200, _RELOCATION_POM),
            }
        )
        findings = self._run_with_transport(checker, (lib,), transport)
        assert all(f.signal == HealthSignal.RELOCATED for f in findings)


class TestInactivity:
    def _checker(self) -> LibraryHealthChecker:
        return LibraryHealthChecker(reference_date=_TODAY)

    def _run_with_transport(
        self, checker: LibraryHealthChecker, libraries: tuple[Library, ...], transport: Any
    ) -> tuple:
        async def _inner() -> tuple:
            async with httpx.AsyncClient(transport=transport, timeout=15.0) as client:
                results = await checker._run_http_checks(client, list(libraries))
            return tuple(results)

        return asyncio.get_event_loop().run_until_complete(_inner())

    def test_inactive_library_produces_finding(self) -> None:
        checker = self._checker()
        lib = _lib("old-lib", "com.example", "old-lib", "1.0.0")
        transport = _mock_transport(
            {
                "old-lib-1.0.0.pom": (200, _EMPTY_POM),
                "maven-metadata.xml": (200, _INACTIVE_METADATA),
            }
        )
        findings = self._run_with_transport(checker, (lib,), transport)
        assert len(findings) == 1
        f = findings[0]
        assert f.signal == HealthSignal.INACTIVE
        # 2026-05-04 - 2020-01-01 ~= 2314 days -> HIGH (>= 1095)
        assert f.severity == LibraryHealthSeverity.HIGH

    def test_recent_library_no_finding(self) -> None:
        checker = self._checker()
        lib = _lib("recent-lib", "com.example", "recent-lib", "1.0.0")
        transport = _mock_transport(
            {
                "recent-lib-1.0.0.pom": (200, _EMPTY_POM),
                "maven-metadata.xml": (200, _RECENT_METADATA),
            }
        )
        findings = self._run_with_transport(checker, (lib,), transport)
        assert len(findings) == 0

    def test_google_library_skips_inactivity(self) -> None:
        checker = self._checker()
        lib = _lib("compose-ui", "androidx.compose.ui", "ui", "1.0.0")
        # metadata would 404 anyway, but we verify no finding is produced
        transport = _mock_transport(
            {
                "ui-1.0.0.pom": (200, _EMPTY_POM),
            }
        )
        findings = self._run_with_transport(checker, (lib,), transport)
        assert len(findings) == 0

    def test_pom_404_returns_no_relocation(self) -> None:
        checker = self._checker()
        lib = _lib("unknown", "com.example", "unknown", "1.0.0")
        transport = _mock_transport({})  # all 404
        findings = self._run_with_transport(checker, (lib,), transport)
        # No relocation, no metadata → no finding
        assert len(findings) == 0


# ---------------------------------------------------------------------------
# Multiple libraries — parallel execution
# ---------------------------------------------------------------------------


class TestMultipleLibraries:
    def _checker(self) -> LibraryHealthChecker:
        return LibraryHealthChecker(reference_date=_TODAY)

    def test_multiple_curated_findings(self) -> None:
        checker = self._checker()
        libs = (
            _lib("butterknife", "com.jakewharton", "butterknife"),
            _lib("rxjava1", "io.reactivex", "rxjava"),
            _lib("okhttp", "com.squareup.okhttp3", "okhttp"),
        )
        with patch.object(checker, "_run_http_checks", return_value=[]):
            findings = _run(checker.check(libs))
        # butterknife and rxjava1 are curated; okhttp is not
        curated = [f for f in findings if f.signal == HealthSignal.CURATED]
        assert len(curated) == 2

    def test_mixed_curated_and_http(self) -> None:
        checker = self._checker()
        curated_lib = _lib("butterknife", "com.jakewharton", "butterknife")
        non_curated_lib = _lib("okhttp", "com.squareup.okhttp3", "okhttp")
        with patch.object(checker, "_run_http_checks", return_value=[]) as mock_http:
            _run(checker.check((curated_lib, non_curated_lib)))
        # HTTP should be called with only the non-curated library
        mock_http.assert_called_once()
        call_args = mock_http.call_args
        http_libs = call_args[0][1]  # second positional arg is the libraries list
        assert len(http_libs) == 1
        assert http_libs[0].alias == "okhttp"
