"""Unit tests for MavenVersionStatusResolver (RFC-0013).

Uses an in-process stub HTTP transport so we never hit the real
Maven registries. The resolver constructs registries internally with
the shared httpx client we control here.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest

from gradle_deps_monitor.domain.catalog import Library
from gradle_deps_monitor.domain.version import MavenVersion
from gradle_deps_monitor.domain.version_status import VersionDrift
from gradle_deps_monitor.infrastructure.resolvers.maven_version_status_resolver import (
    MavenVersionStatusResolver,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _lib(alias: str, group: str, artifact: str, version: str) -> Library:
    return Library(alias=alias, group=group, artifact=artifact, version=MavenVersion(version))


def _xml(release: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f"<metadata><versioning><release>{release}</release></versioning></metadata>"
    )


class _StubTransport(httpx.AsyncBaseTransport):
    """In-process httpx transport mapping URL → ``(status, body)``.

    Any URL not in the routing table returns 404 so the resolver can
    exercise its fallback path.
    """

    def __init__(self, routes: dict[str, tuple[int, str]]) -> None:
        self.routes = routes
        self.calls: list[str] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        self.calls.append(url)
        status, body = self.routes.get(url, (404, ""))
        return httpx.Response(status_code=status, text=body)


def _patch_client(monkeypatch: pytest.MonkeyPatch, transport: _StubTransport) -> None:
    """Force every ``httpx.AsyncClient`` to use our stub transport."""
    real_init = httpx.AsyncClient.__init__

    def _init(self: httpx.AsyncClient, *args: object, **kwargs: object) -> None:
        kwargs["transport"] = transport
        real_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", _init)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_empty_libraries_returns_empty(tmp_path: Path) -> None:
    resolver = MavenVersionStatusResolver(cache_dir=tmp_path)
    result = asyncio.run(resolver.resolve(()))
    assert result == ()


def test_resolves_androidx_against_google_maven_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    google_url = "https://dl.google.com/dl/android/maven2/androidx/core/core-ktx/maven-metadata.xml"
    transport = _StubTransport({google_url: (200, _xml("1.13.0"))})
    _patch_client(monkeypatch, transport)

    resolver = MavenVersionStatusResolver(cache_dir=tmp_path)
    [status] = asyncio.run(
        resolver.resolve((_lib("core-ktx", "androidx.core", "core-ktx", "1.10.0"),))
    )

    assert status.alias == "core-ktx"
    assert status.latest is not None
    assert status.latest.raw == "1.13.0"
    assert status.drift == VersionDrift.MINOR
    # Google Maven is the only one called for an androidx group on success.
    assert any("dl.google.com" in c for c in transport.calls)
    assert not any("repo1.maven.org" in c for c in transport.calls)


def test_resolves_third_party_against_maven_central_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    central = "https://repo1.maven.org/maven2/com/squareup/okhttp3/okhttp/maven-metadata.xml"
    transport = _StubTransport({central: (200, _xml("4.12.0"))})
    _patch_client(monkeypatch, transport)

    resolver = MavenVersionStatusResolver(cache_dir=tmp_path)
    [status] = asyncio.run(
        resolver.resolve((_lib("okhttp", "com.squareup.okhttp3", "okhttp", "4.9.1"),))
    )

    assert status.latest is not None
    assert status.latest.raw == "4.12.0"
    assert status.drift == VersionDrift.MINOR
    assert any("repo1.maven.org" in c for c in transport.calls)
    assert not any("dl.google.com" in c for c in transport.calls)


def test_falls_back_to_secondary_on_404(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # ``com.google.*`` is Google-first. Google 404s; fall back to Maven Central.
    google_url = "https://dl.google.com/dl/android/maven2/com/google/example/lib/maven-metadata.xml"
    central_url = "https://repo1.maven.org/maven2/com/google/example/lib/maven-metadata.xml"
    transport = _StubTransport(
        {
            google_url: (404, ""),
            central_url: (200, _xml("3.0.0")),
        }
    )
    _patch_client(monkeypatch, transport)

    resolver = MavenVersionStatusResolver(cache_dir=tmp_path)
    [status] = asyncio.run(
        resolver.resolve(
            (
                Library(
                    alias="lib",
                    group="com.google.example",
                    artifact="lib",
                    version=MavenVersion("1.0.0"),
                ),
            )
        )
    )

    assert status.latest is not None
    assert status.latest.raw == "3.0.0"
    assert status.drift == VersionDrift.MAJOR
    # Both registries were tried (primary 404'd, fell back to secondary)
    assert any("dl.google.com" in c for c in transport.calls)
    assert any("repo1.maven.org" in c for c in transport.calls)


def test_unknown_drift_when_both_registries_404(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    transport = _StubTransport({})  # everything 404s
    _patch_client(monkeypatch, transport)

    resolver = MavenVersionStatusResolver(cache_dir=tmp_path)
    [status] = asyncio.run(resolver.resolve((_lib("ghost", "io.example", "ghost", "1.0.0"),)))

    assert status.latest is None
    assert status.drift == VersionDrift.UNKNOWN
    # Both registries were tried
    assert any("dl.google.com" in c for c in transport.calls)
    assert any("repo1.maven.org" in c for c in transport.calls)


def test_preserves_input_order(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    transport = _StubTransport(
        {
            "https://repo1.maven.org/maven2/io/example/a/maven-metadata.xml": (200, _xml("1.0.0")),
            "https://repo1.maven.org/maven2/io/example/b/maven-metadata.xml": (200, _xml("2.0.0")),
            "https://repo1.maven.org/maven2/io/example/c/maven-metadata.xml": (200, _xml("3.0.0")),
        }
    )
    _patch_client(monkeypatch, transport)

    resolver = MavenVersionStatusResolver(cache_dir=tmp_path)
    libs = (
        _lib("a", "io.example", "a", "1.0.0"),
        _lib("b", "io.example", "b", "1.0.0"),
        _lib("c", "io.example", "c", "1.0.0"),
    )
    statuses = asyncio.run(resolver.resolve(libs))
    assert tuple(s.alias for s in statuses) == ("a", "b", "c")
