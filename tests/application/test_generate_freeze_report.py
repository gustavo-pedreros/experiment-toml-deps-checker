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
