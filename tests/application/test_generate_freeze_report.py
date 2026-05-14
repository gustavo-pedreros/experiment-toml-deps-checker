"""Unit tests for GenerateFreezeReport use case.

Uses a hand-rolled stub that satisfies the CatalogParser Protocol —
no mocking framework, no filesystem access.
"""

from __future__ import annotations

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


def test_execute_returns_freeze_report(empty_catalog: Catalog) -> None:
    use_case = GenerateFreezeReport(_OkParser(empty_catalog))
    result = use_case.execute(Path("/some/path"))
    assert isinstance(result, FreezeReport)


def test_execute_report_contains_parsed_catalog(catalog_with_libs: Catalog) -> None:
    use_case = GenerateFreezeReport(_OkParser(catalog_with_libs))
    result = use_case.execute(Path("/some/path"))
    assert result.catalog is catalog_with_libs


def test_execute_forwards_path_to_parser(empty_catalog: Catalog) -> None:
    stub = _OkParser(empty_catalog)
    use_case = GenerateFreezeReport(stub)
    expected = Path("/gradle/libs.versions.toml")
    use_case.execute(expected)
    assert stub.last_path == expected


def test_execute_report_generated_at_is_utc(empty_catalog: Catalog) -> None:
    use_case = GenerateFreezeReport(_OkParser(empty_catalog))
    before = datetime.now(tz=UTC)
    result = use_case.execute(Path("/some/path"))
    after = datetime.now(tz=UTC)
    assert before <= result.generated_at <= after


def test_execute_propagates_parse_error() -> None:
    use_case = GenerateFreezeReport(_FailParser())
    with pytest.raises(CatalogParseError, match="simulated parse failure"):
        use_case.execute(Path("/some/path"))


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


def test_execute_populates_health_findings_when_checker_provided(
    empty_catalog: Catalog,
) -> None:
    checker = _FixedChecker((_FINDING,))
    use_case = GenerateFreezeReport(_OkParser(empty_catalog), health_checker=checker)
    result = use_case.execute(Path("/some/path"))
    assert result.health_findings == (_FINDING,)


def test_execute_health_findings_empty_without_checker(empty_catalog: Catalog) -> None:
    use_case = GenerateFreezeReport(_OkParser(empty_catalog))
    result = use_case.execute(Path("/some/path"))
    assert result.health_findings == ()


def test_execute_passes_parsed_catalog_to_checker(empty_catalog: Catalog) -> None:
    received: list[Catalog] = []

    def _recorder(catalog: Catalog) -> tuple[Finding, ...]:
        received.append(catalog)
        return ()

    use_case = GenerateFreezeReport(_OkParser(empty_catalog), health_checker=_recorder)
    use_case.execute(Path("/some/path"))
    assert received == [empty_catalog]


# ---------------------------------------------------------------------------
# Risk score weight / threshold injection (RFC-0012)
# ---------------------------------------------------------------------------


def test_execute_propagates_risk_weights_to_score(catalog_with_libs: Catalog) -> None:
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
    report = use_case.execute(Path("/some/path"))

    assert report.risk_score_report is not None
    assert report.risk_score_report.weights == custom_weights
    assert report.risk_score_report.thresholds == custom_thresholds


def test_execute_uses_default_weights_when_none_provided(
    catalog_with_libs: Catalog,
) -> None:
    from gradle_deps_monitor.domain.risk_score import RiskThresholds, RiskWeights

    use_case = GenerateFreezeReport(_OkParser(catalog_with_libs), enable_risk_score=True)
    report = use_case.execute(Path("/some/path"))

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

    def scan(self, catalog_path, catalog):  # type: ignore[no-untyped-def]
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


def test_scanner_findings_merged_into_health_findings(catalog_with_libs: Catalog) -> None:
    """RFC-0019 PR #1: scanner-emitted findings reach the report."""
    scanner = _ScannerEmittingMod001()
    use_case = GenerateFreezeReport(_OkParser(catalog_with_libs), module_usage_scanner=scanner)
    report = use_case.execute(Path("/some/path"))

    assert scanner.scanned
    rule_ids = [f.rule_id for f in report.health_findings]
    assert "MOD-001" in rule_ids


def test_scanner_findings_appended_after_existing_health_findings(
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
    report = use_case.execute(Path("/some/path"))

    rule_ids = [f.rule_id for f in report.health_findings]
    assert rule_ids == ["HDX-005", "MOD-001"]
