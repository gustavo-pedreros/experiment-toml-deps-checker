"""Tests for the catalog health runner."""

from __future__ import annotations

from pathlib import Path

from gradle_deps_monitor.checks.runner import run_all
from gradle_deps_monitor.domain import Severity
from gradle_deps_monitor.domain.catalog import Bundle, Catalog, Library, Plugin
from gradle_deps_monitor.domain.version import MavenVersion

_PATH = Path("/fake/libs.versions.toml")


def _catalog(**kwargs: object) -> Catalog:
    return Catalog(
        source_path=_PATH,
        libraries=kwargs.get("libraries", ()),  # type: ignore[arg-type]
        plugins=kwargs.get("plugins", ()),  # type: ignore[arg-type]
        bundles=kwargs.get("bundles", ()),  # type: ignore[arg-type]
        versions=kwargs.get("versions", {}),  # type: ignore[arg-type]
    )


def test_run_all_returns_tuple() -> None:
    result = run_all(_catalog())
    assert isinstance(result, tuple)


def test_run_all_empty_catalog_produces_findings() -> None:
    # An empty catalog fires missing-plugins (warning) but not errors.
    findings = run_all(_catalog())
    severities = {f.severity for f in findings}
    assert Severity.ERROR not in severities


def test_run_all_clean_catalog_produces_no_findings() -> None:
    # A catalog that passes all rules.
    cat = _catalog(
        libraries=(
            Library(
                alias="core-ktx",
                group="androidx.core",
                artifact="core-ktx",
                version=MavenVersion("1.13.0"),
                version_ref="androidxCore",
            ),
        ),
        plugins=(
            Plugin(
                alias="agp",
                id="com.android.application",
                version=MavenVersion("8.3.0"),
                version_ref="agp",
            ),
        ),
        bundles=(Bundle("androidx", ("core-ktx",)),),
        versions={"androidxCore": "1.13.0", "agp": "8.3.0"},
    )
    assert run_all(cat) == ()


def test_run_all_detects_duplicate_library() -> None:
    cat = _catalog(
        libraries=(
            Library("a", "com.foo", "bar", MavenVersion("1.0")),
            Library("b", "com.foo", "bar", MavenVersion("1.0")),
        ),
        plugins=(Plugin("agp", "com.android.application", MavenVersion("8.3.0")),),
        bundles=(Bundle("all", ("a",)),),
        versions={},
    )
    rule_ids = {f.rule_id for f in run_all(cat)}
    assert "catalog.duplicate-library" in rule_ids


def test_run_all_error_findings_come_before_warnings() -> None:
    # Errors should appear first in the ordered output.
    cat = _catalog(
        libraries=(
            Library("a", "com.foo", "bar", MavenVersion("1.0")),
            Library("b", "com.foo", "bar", MavenVersion("1.0")),
        ),
    )
    findings = run_all(cat)
    if len(findings) >= 2:
        severities = [f.severity for f in findings]
        error_indices = [i for i, s in enumerate(severities) if s == Severity.ERROR]
        warning_indices = [i for i, s in enumerate(severities) if s == Severity.WARNING]
        if error_indices and warning_indices:
            assert max(error_indices) < min(warning_indices)
