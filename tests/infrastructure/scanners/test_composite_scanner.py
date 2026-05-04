"""Unit tests for CompositeScanner."""

from __future__ import annotations

import pytest

from gradle_deps_monitor.domain.advisory import Advisory, AdvisorySeverity, LibraryAdvisory
from gradle_deps_monitor.domain.catalog import Library
from gradle_deps_monitor.domain.version import MavenVersion
from gradle_deps_monitor.infrastructure.scanners.composite_scanner import (
    CompositeScanner,
    _deduplicate,
)

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _make_lib(
    alias: str, group: str = "com.example", artifact: str = "", version: str = "1.0.0"
) -> Library:
    return Library(
        alias=alias,
        group=group,
        artifact=artifact or alias,
        version=MavenVersion(version),
    )


def _advisory(
    ghsa_id: str = "GHSA-test",
    cve_id: str | None = None,
    severity: AdvisorySeverity = AdvisorySeverity.HIGH,
    fixed_version: str | None = None,
    source: str = "github",
) -> Advisory:
    return Advisory(
        ghsa_id=ghsa_id,
        cve_id=cve_id,
        severity=severity,
        summary="Test advisory",
        fixed_version=fixed_version,
        url="https://example.com",
        source=source,
    )


def _lib_advisory(lib: Library, *advisories: Advisory) -> LibraryAdvisory:
    return LibraryAdvisory(
        alias=lib.alias,
        coordinate=f"{lib.group}:{lib.artifact}",
        version=str(lib.version),
        advisories=advisories,
    )


class _StubScanner:
    """Simple stub that returns pre-canned results."""

    def __init__(self, results: dict[str, tuple[Advisory, ...]]) -> None:
        # key = library alias → advisories to return
        self._results = results

    async def scan(self, libraries: tuple[Library, ...]) -> tuple[LibraryAdvisory, ...]:
        return tuple(
            LibraryAdvisory(
                alias=lib.alias,
                coordinate=f"{lib.group}:{lib.artifact}",
                version=str(lib.version),
                advisories=self._results.get(lib.alias, ()),
            )
            for lib in libraries
        )


# ---------------------------------------------------------------------------
# _deduplicate helper
# ---------------------------------------------------------------------------


class TestDeduplicate:
    def test_no_duplicates_unchanged(self) -> None:
        a1 = _advisory(ghsa_id="GHSA-aaa", cve_id="CVE-2023-001")
        a2 = _advisory(ghsa_id="GHSA-bbb", cve_id="CVE-2023-002")
        result = _deduplicate([a1, a2])
        assert len(result) == 2

    def test_deduplicates_by_cve_id(self) -> None:
        a1 = _advisory(ghsa_id="GHSA-aaa", cve_id="CVE-2023-001", source="github")
        a2 = _advisory(ghsa_id="sonatype-xxx", cve_id="CVE-2023-001", source="oss_index")
        result = _deduplicate([a1, a2])
        assert len(result) == 1
        assert result[0].ghsa_id == "GHSA-aaa"  # first seen wins

    def test_prefers_advisory_with_fixed_version_over_first_seen(self) -> None:
        a1 = _advisory(cve_id="CVE-2023-001", fixed_version=None, source="oss_index")
        a2 = _advisory(cve_id="CVE-2023-001", fixed_version="2.0.0", source="github")
        result = _deduplicate([a1, a2])
        assert len(result) == 1
        assert result[0].fixed_version == "2.0.0"

    def test_deduplicates_by_ghsa_id_when_no_cve(self) -> None:
        a1 = _advisory(ghsa_id="GHSA-aaa", cve_id=None, source="github")
        a2 = _advisory(ghsa_id="GHSA-aaa", cve_id=None, source="other")
        result = _deduplicate([a1, a2])
        assert len(result) == 1

    def test_different_ghsa_ids_without_cve_are_kept(self) -> None:
        a1 = _advisory(ghsa_id="GHSA-aaa", cve_id=None)
        a2 = _advisory(ghsa_id="GHSA-bbb", cve_id=None)
        result = _deduplicate([a1, a2])
        assert len(result) == 2

    def test_empty_list(self) -> None:
        assert _deduplicate([]) == []


# ---------------------------------------------------------------------------
# CompositeScanner
# ---------------------------------------------------------------------------


class TestCompositeScanner:
    @pytest.mark.asyncio
    async def test_empty_scanners_returns_no_advisories(self) -> None:
        scanner = CompositeScanner(scanners=())
        libs = (_make_lib("lib-a"),)
        results = await scanner.scan(libs)
        assert len(results) == 1
        assert results[0].is_vulnerable is False

    @pytest.mark.asyncio
    async def test_single_scanner_passthrough(self) -> None:
        adv = _advisory(cve_id="CVE-2023-001")
        stub = _StubScanner({"lib-a": (adv,)})
        scanner = CompositeScanner(scanners=(stub,))

        lib = _make_lib("lib-a")
        results = await scanner.scan((lib,))

        assert results[0].is_vulnerable is True
        assert results[0].advisories[0].cve_id == "CVE-2023-001"

    @pytest.mark.asyncio
    async def test_merges_unique_advisories_from_two_scanners(self) -> None:
        adv_gh = _advisory(ghsa_id="GHSA-aaa", cve_id="CVE-2023-001", source="github")
        adv_oss = _advisory(ghsa_id="sonatype-yyy", cve_id="CVE-2023-002", source="oss_index")

        stub_gh = _StubScanner({"lib-a": (adv_gh,)})
        stub_oss = _StubScanner({"lib-a": (adv_oss,)})
        scanner = CompositeScanner(scanners=(stub_gh, stub_oss))

        lib = _make_lib("lib-a")
        results = await scanner.scan((lib,))

        assert len(results[0].advisories) == 2

    @pytest.mark.asyncio
    async def test_deduplicates_same_cve_from_two_scanners(self) -> None:
        adv_gh = _advisory(
            ghsa_id="GHSA-aaa", cve_id="CVE-2023-001", fixed_version="2.0.0", source="github"
        )
        adv_oss = _advisory(
            ghsa_id="sonatype-xxx", cve_id="CVE-2023-001", fixed_version=None, source="oss_index"
        )

        stub_gh = _StubScanner({"lib-a": (adv_gh,)})
        stub_oss = _StubScanner({"lib-a": (adv_oss,)})
        scanner = CompositeScanner(scanners=(stub_gh, stub_oss))

        lib = _make_lib("lib-a")
        results = await scanner.scan((lib,))

        # Deduplicated to one advisory; the github one (with fixed_version) is kept.
        assert len(results[0].advisories) == 1
        assert results[0].advisories[0].fixed_version == "2.0.0"
        assert results[0].advisories[0].source == "github"

    @pytest.mark.asyncio
    async def test_preserves_library_order(self) -> None:
        stub = _StubScanner({})
        scanner = CompositeScanner(scanners=(stub,))

        libs = tuple(_make_lib(f"lib-{i}") for i in range(5))
        results = await scanner.scan(libs)

        assert [r.alias for r in results] == [lib.alias for lib in libs]

    @pytest.mark.asyncio
    async def test_scans_multiple_libraries_independently(self) -> None:
        adv = _advisory(cve_id="CVE-2023-001")
        stub = _StubScanner({"vulnerable-lib": (adv,)})
        scanner = CompositeScanner(scanners=(stub,))

        libs = (_make_lib("vulnerable-lib"), _make_lib("safe-lib"))
        results = await scanner.scan(libs)

        assert results[0].is_vulnerable is True
        assert results[1].is_vulnerable is False

    @pytest.mark.asyncio
    async def test_oss_only_advisory_with_no_cve_kept(self) -> None:
        """Non-CVE advisory from OSS Index should appear in results."""
        adv_oss = _advisory(ghsa_id="sonatype-yyy", cve_id=None, source="oss_index")
        stub_oss = _StubScanner({"lib-a": (adv_oss,)})
        scanner = CompositeScanner(scanners=(stub_oss,))

        lib = _make_lib("lib-a")
        results = await scanner.scan((lib,))

        assert len(results[0].advisories) == 1
        assert results[0].advisories[0].ghsa_id == "sonatype-yyy"

    @pytest.mark.asyncio
    async def test_composite_runs_scanners_concurrently(self) -> None:
        """Both scanners should be called (not short-circuited)."""
        called: list[str] = []

        class TrackingScanner:
            def __init__(self, name: str) -> None:
                self._name = name

            async def scan(self, libraries: tuple[Library, ...]) -> tuple[LibraryAdvisory, ...]:
                called.append(self._name)
                return tuple(
                    LibraryAdvisory(
                        alias=lib.alias,
                        coordinate=f"{lib.group}:{lib.artifact}",
                        version=str(lib.version),
                        advisories=(),
                    )
                    for lib in libraries
                )

        scanner = CompositeScanner(scanners=(TrackingScanner("gh"), TrackingScanner("oss")))
        await scanner.scan((_make_lib("lib-a"),))

        assert "gh" in called
        assert "oss" in called
