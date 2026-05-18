"""Unit tests for GenerateFreezeReport use case.

Uses a hand-rolled stub that satisfies the CatalogParser Protocol —
no mocking framework, no filesystem access.
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

from gradle_deps_monitor.application.generate_freeze_report import GenerateFreezeReport
from gradle_deps_monitor.application.ports.catalog_parser import CatalogParseError
from gradle_deps_monitor.domain import (
    Catalog,
    Finding,
    FreezeReport,
    Library,
    MavenVersion,
    Severity,
)

# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------


class _OkParser:
    """Always returns the injected catalog regardless of path."""

    def __init__(self, catalog: Catalog) -> None:
        self._catalog = catalog
        self.last_path: Path | None = None

    def parse(self, path: Path) -> Catalog:
        self.last_path = path
        return self._catalog


class _FailParser:
    """Always raises CatalogParseError."""

    def parse(self, path: Path) -> Catalog:
        raise CatalogParseError("simulated parse failure")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def empty_catalog() -> Catalog:
    return Catalog(
        source_path=Path("/fake/libs.versions.toml"),
        libraries=(),
        plugins=(),
        bundles=(),
    )


@pytest.fixture()
def catalog_with_libs() -> Catalog:
    return Catalog(
        source_path=Path("/fake/libs.versions.toml"),
        libraries=(
            Library(
                alias="kotlin-stdlib",
                group="org.jetbrains.kotlin",
                artifact="kotlin-stdlib",
                version=MavenVersion("2.0.0"),
            ),
        ),
        plugins=(),
        bundles=(),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_execute_returns_freeze_report(empty_catalog: Catalog) -> None:
    use_case = GenerateFreezeReport(_OkParser(empty_catalog))
    result = await use_case.execute(Path("/some/path"))
    assert isinstance(result, FreezeReport)


async def test_execute_report_contains_parsed_catalog(catalog_with_libs: Catalog) -> None:
    use_case = GenerateFreezeReport(_OkParser(catalog_with_libs))
    result = await use_case.execute(Path("/some/path"))
    assert result.catalog is catalog_with_libs


async def test_execute_forwards_path_to_parser(empty_catalog: Catalog) -> None:
    stub = _OkParser(empty_catalog)
    use_case = GenerateFreezeReport(stub)
    expected = Path("/gradle/libs.versions.toml")
    await use_case.execute(expected)
    assert stub.last_path == expected


async def test_execute_report_generated_at_is_utc(empty_catalog: Catalog) -> None:
    use_case = GenerateFreezeReport(_OkParser(empty_catalog))
    before = datetime.now(tz=UTC)
    result = await use_case.execute(Path("/some/path"))
    after = datetime.now(tz=UTC)
    assert before <= result.generated_at <= after


async def test_execute_propagates_parse_error() -> None:
    use_case = GenerateFreezeReport(_FailParser())
    with pytest.raises(CatalogParseError, match="simulated parse failure"):
        await use_case.execute(Path("/some/path"))


# ---------------------------------------------------------------------------
# Health checker injection
# ---------------------------------------------------------------------------

_FINDING = Finding(rule_id="catalog.test", severity=Severity.INFO, message="test finding")


class _FixedChecker:
    """Always returns a fixed tuple of findings."""

    def __init__(self, findings: tuple[Finding, ...]) -> None:
        self._findings = findings

    def __call__(self, catalog: Catalog) -> tuple[Finding, ...]:
        return self._findings


async def test_execute_populates_health_findings_when_checker_provided(
    empty_catalog: Catalog,
) -> None:
    checker = _FixedChecker((_FINDING,))
    use_case = GenerateFreezeReport(_OkParser(empty_catalog), health_checker=checker)
    result = await use_case.execute(Path("/some/path"))
    assert result.health_findings == (_FINDING,)


async def test_execute_health_findings_empty_without_checker(empty_catalog: Catalog) -> None:
    use_case = GenerateFreezeReport(_OkParser(empty_catalog))
    result = await use_case.execute(Path("/some/path"))
    assert result.health_findings == ()


async def test_execute_passes_parsed_catalog_to_checker(empty_catalog: Catalog) -> None:
    received: list[Catalog] = []

    def _recorder(catalog: Catalog) -> tuple[Finding, ...]:
        received.append(catalog)
        return ()

    use_case = GenerateFreezeReport(_OkParser(empty_catalog), health_checker=_recorder)
    await use_case.execute(Path("/some/path"))
    assert received == [empty_catalog]


# ---------------------------------------------------------------------------
# Risk score weight / threshold injection (RFC-0012)
# ---------------------------------------------------------------------------


async def test_execute_propagates_risk_weights_to_score(catalog_with_libs: Catalog) -> None:
    """Custom :class:`RiskWeights` must reach :class:`RiskScoreReport.weights`."""
    from gradle_deps_monitor.domain.risk_score import RiskThresholds, RiskWeights

    custom_weights = RiskWeights(
        outdatedness=20,
        cve=40,
        abandonment=15,
        blast_radius=10,
        compliance=10,
        license=5,
    )
    custom_thresholds = RiskThresholds(critical=80, high=60, medium=40)

    use_case = GenerateFreezeReport(
        _OkParser(catalog_with_libs),
        enable_risk_score=True,
        risk_weights=custom_weights,
        risk_thresholds=custom_thresholds,
    )
    report = await use_case.execute(Path("/some/path"))

    assert report.risk_score_report is not None
    assert report.risk_score_report.weights == custom_weights
    assert report.risk_score_report.thresholds == custom_thresholds


async def test_execute_uses_default_weights_when_none_provided(
    catalog_with_libs: Catalog,
) -> None:
    from gradle_deps_monitor.domain.risk_score import RiskThresholds, RiskWeights

    use_case = GenerateFreezeReport(_OkParser(catalog_with_libs), enable_risk_score=True)
    report = await use_case.execute(Path("/some/path"))

    assert report.risk_score_report is not None
    assert report.risk_score_report.weights == RiskWeights()
    assert report.risk_score_report.thresholds == RiskThresholds()


# ---------------------------------------------------------------------------
# RFC-0019 PR #1 — scanner findings are merged into health_findings
# ---------------------------------------------------------------------------


class _ScannerEmittingMod001:
    """Stub ModuleUsageScanner that returns a map carrying a MOD-001 finding.

    Models the production scenario where one module's build file is
    unreadable: the scanner returns a map for the modules that DID
    read, plus a ``MOD-001`` Finding for the one that didn't. The
    application layer must promote that finding into
    ``FreezeReport.health_findings`` per the RFC-0019 contract.
    """

    def __init__(self) -> None:
        self.scanned = False

    async def scan(self, catalog_path, catalog):  # type: ignore[no-untyped-def]
        from gradle_deps_monitor.domain.module_usage import ModuleUsageMap

        self.scanned = True
        return ModuleUsageMap(
            library_usages=(),
            module_summaries=(),
            modules_scanned=0,
            findings=(
                Finding(
                    rule_id="MOD-001",
                    severity=Severity.WARNING,
                    message="Could not read build file for module `:corrupt`: UnicodeDecodeError",
                ),
            ),
        )


async def test_scanner_findings_merged_into_health_findings(catalog_with_libs: Catalog) -> None:
    """RFC-0019 PR #1: scanner-emitted findings reach the report."""
    scanner = _ScannerEmittingMod001()
    use_case = GenerateFreezeReport(_OkParser(catalog_with_libs), module_usage_scanner=scanner)
    report = await use_case.execute(Path("/some/path"))

    assert scanner.scanned
    rule_ids = [f.rule_id for f in report.health_findings]
    assert "MOD-001" in rule_ids


async def test_scanner_findings_appended_after_existing_health_findings(
    catalog_with_libs: Catalog,
) -> None:
    """Health checker findings come first; scanner findings are appended."""

    def health_check(_catalog):  # type: ignore[no-untyped-def]
        return (Finding(rule_id="HDX-005", severity=Severity.WARNING, message="orphan"),)

    scanner = _ScannerEmittingMod001()
    use_case = GenerateFreezeReport(
        _OkParser(catalog_with_libs),
        health_checker=health_check,
        module_usage_scanner=scanner,
    )
    report = await use_case.execute(Path("/some/path"))

    rule_ids = [f.rule_id for f in report.health_findings]
    assert rule_ids == ["HDX-005", "MOD-001"]


# ---------------------------------------------------------------------------
# RFC-0025 — concurrency proof for Phase 1 fan-out
# ---------------------------------------------------------------------------

_FAKE_ADAPTER_SLEEP_S = 0.05


class _SleepyVulnScanner:
    async def scan(self, libraries):  # type: ignore[no-untyped-def]
        await asyncio.sleep(_FAKE_ADAPTER_SLEEP_S)
        return ()


class _SleepyLibraryHealthChecker:
    async def check(self, libraries):  # type: ignore[no-untyped-def]
        await asyncio.sleep(_FAKE_ADAPTER_SLEEP_S)
        return ()


class _SleepyChangelogFetcher:
    async def fetch(self, libraries):  # type: ignore[no-untyped-def]
        from gradle_deps_monitor.domain.changelog import ChangelogFetchStats

        await asyncio.sleep(_FAKE_ADAPTER_SLEEP_S)
        return (), ChangelogFetchStats()


class _SleepyModuleUsageScanner:
    async def scan(self, catalog_path, catalog):  # type: ignore[no-untyped-def]
        from gradle_deps_monitor.domain.module_usage import ModuleUsageMap

        await asyncio.sleep(_FAKE_ADAPTER_SLEEP_S)
        return ModuleUsageMap(
            library_usages=(), module_summaries=(), modules_scanned=0, findings=()
        )


class _SleepyLicenseChecker:
    async def check(self, libraries):  # type: ignore[no-untyped-def]
        from gradle_deps_monitor.domain.license import LicenseAudit

        await asyncio.sleep(_FAKE_ADAPTER_SLEEP_S)
        return LicenseAudit(findings=(), libraries_audited=0)


class _SleepyVersionStatusResolver:
    async def resolve(self, libraries):  # type: ignore[no-untyped-def]
        await asyncio.sleep(_FAKE_ADAPTER_SLEEP_S)
        return ()


# ---------------------------------------------------------------------------
# RFC-0028 — security_scanned flag is set from scanner presence
# ---------------------------------------------------------------------------


class _NullScanner:
    async def scan(self, libraries):  # type: ignore[no-untyped-def]
        return ()


async def test_execute_sets_security_scanned_true_when_scanner_injected(
    empty_catalog: Catalog,
) -> None:
    """RFC-0028: flag reflects adapter presence at construction time."""
    use_case = GenerateFreezeReport(_OkParser(empty_catalog), vulnerability_scanner=_NullScanner())
    report = await use_case.execute(Path("/some/path"))
    assert report.security_scanned is True


async def test_execute_sets_security_scanned_false_when_scanner_absent(
    empty_catalog: Catalog,
) -> None:
    use_case = GenerateFreezeReport(_OkParser(empty_catalog))  # no scanner
    report = await use_case.execute(Path("/some/path"))
    assert report.security_scanned is False


async def test_phase1_adapters_run_concurrently(empty_catalog: Catalog) -> None:
    """RFC-0025: the six Phase 1 adapters fan out via ``asyncio.gather``.

    Each fake adapter sleeps ``_FAKE_ADAPTER_SLEEP_S`` (50 ms) in its
    async method. With six adapters, sequential execution would take
    ~300 ms; the parallel fan-out should complete in roughly
    ``max(t_i)`` plus overhead — well under 200 ms with comfortable
    slack for CI noise.

    The assertion compares wall-clock against ``serial_baseline / 2`` so
    a regression to per-stage awaits would fail loudly without flaking
    on a slow runner.
    """
    n_adapters = 6
    serial_baseline = n_adapters * _FAKE_ADAPTER_SLEEP_S

    use_case = GenerateFreezeReport(
        _OkParser(empty_catalog),
        vulnerability_scanner=_SleepyVulnScanner(),
        library_health_checker=_SleepyLibraryHealthChecker(),
        changelog_fetcher=_SleepyChangelogFetcher(),
        module_usage_scanner=_SleepyModuleUsageScanner(),
        license_checker=_SleepyLicenseChecker(),
        version_status_resolver=_SleepyVersionStatusResolver(),
    )

    start = time.monotonic()
    await use_case.execute(Path("/some/path"))
    elapsed = time.monotonic() - start

    assert elapsed < serial_baseline / 2, (
        f"Phase 1 fan-out regressed to serial execution: "
        f"elapsed={elapsed:.3f}s, serial_baseline={serial_baseline:.3f}s"
    )
    # Sanity: the sleeps actually happened (not all returning instantly).
    assert elapsed >= _FAKE_ADAPTER_SLEEP_S
