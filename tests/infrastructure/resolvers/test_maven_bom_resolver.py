"""Unit tests for MavenBomResolver (RFC-0014).

Uses an in-process httpx transport so we never hit the real Maven
registries.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from gradle_deps_monitor.domain.catalog import Library
from gradle_deps_monitor.domain.version import MavenVersion
from gradle_deps_monitor.infrastructure.resolvers.maven_bom_resolver import MavenBomResolver


def _bom(alias: str, group: str, artifact: str, version: str) -> Library:
    return Library(
        alias=alias,
        group=group,
        artifact=artifact,
        version=MavenVersion(version),
    )


_FIREBASE_POM = """\
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
  <groupId>com.google.firebase</groupId>
  <artifactId>firebase-bom</artifactId>
  <version>33.0.0</version>
  <packaging>pom</packaging>
  <dependencyManagement>
    <dependencies>
      <dependency>
        <groupId>com.google.firebase</groupId>
        <artifactId>firebase-analytics</artifactId>
        <version>21.5.0</version>
      </dependency>
      <dependency>
        <groupId>com.google.firebase</groupId>
        <artifactId>firebase-auth</artifactId>
        <version>23.0.0</version>
      </dependency>
      <dependency>
        <groupId>com.google.firebase</groupId>
        <artifactId>firebase-crashlytics</artifactId>
        <version>19.0.0</version>
      </dependency>
    </dependencies>
  </dependencyManagement>
</project>
"""

_OKHTTP_POM_NO_NS = """\
<?xml version="1.0" encoding="UTF-8"?>
<project>
  <groupId>com.squareup.okhttp3</groupId>
  <artifactId>okhttp-bom</artifactId>
  <version>4.12.0</version>
  <dependencyManagement>
    <dependencies>
      <dependency>
        <groupId>com.squareup.okhttp3</groupId>
        <artifactId>okhttp</artifactId>
        <version>4.12.0</version>
      </dependency>
      <!-- import-scope BoM should be skipped -->
      <dependency>
        <groupId>com.squareup.okio</groupId>
        <artifactId>okio-bom</artifactId>
        <version>3.9.0</version>
        <scope>import</scope>
      </dependency>
    </dependencies>
  </dependencyManagement>
</project>
"""


class _StubTransport(httpx.AsyncBaseTransport):
    def __init__(self, routes: dict[str, tuple[int, str]]) -> None:
        self.routes = routes
        self.calls: list[str] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        self.calls.append(url)
        status, body = self.routes.get(url, (404, ""))
        return httpx.Response(status_code=status, text=body)


def _patch_client(monkeypatch: pytest.MonkeyPatch, transport: _StubTransport) -> None:
    real_init = httpx.AsyncClient.__init__

    def _init(self: httpx.AsyncClient, *args: object, **kwargs: object) -> None:
        kwargs["transport"] = transport
        real_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", _init)


# ---------------------------------------------------------------------------


def test_empty_returns_empty() -> None:
    assert asyncio.run(MavenBomResolver().resolve(())) == ()


def test_resolves_firebase_bom_via_google_maven(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pom_url = (
        "https://dl.google.com/dl/android/maven2/com/google/firebase/"
        "firebase-bom/33.0.0/firebase-bom-33.0.0.pom"
    )
    transport = _StubTransport({pom_url: (200, _FIREBASE_POM)})
    _patch_client(monkeypatch, transport)

    bom = _bom("firebase-bom", "com.google.firebase", "firebase-bom", "33.0.0")
    [resolution] = asyncio.run(MavenBomResolver().resolve((bom,)))

    assert resolution.bom_alias == "firebase-bom"
    assert resolution.bom_version.raw == "33.0.0"
    assert len(resolution.managed) == 3
    aliases = sorted(m.artifact for m in resolution.managed)
    assert aliases == ["firebase-analytics", "firebase-auth", "firebase-crashlytics"]


def test_resolves_third_party_via_maven_central_no_namespace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verifies POMs without the maven4 XML namespace also parse."""
    pom_url = (
        "https://repo1.maven.org/maven2/com/squareup/okhttp3/"
        "okhttp-bom/4.12.0/okhttp-bom-4.12.0.pom"
    )
    transport = _StubTransport({pom_url: (200, _OKHTTP_POM_NO_NS)})
    _patch_client(monkeypatch, transport)

    bom = _bom("okhttp-bom", "com.squareup.okhttp3", "okhttp-bom", "4.12.0")
    [resolution] = asyncio.run(MavenBomResolver().resolve((bom,)))

    # "okio-bom" was scope=import → must be skipped
    assert [m.artifact for m in resolution.managed] == ["okhttp"]


def test_falls_back_to_secondary_on_404(monkeypatch: pytest.MonkeyPatch) -> None:
    google_url = (
        "https://dl.google.com/dl/android/maven2/com/google/firebase/"
        "firebase-bom/33.0.0/firebase-bom-33.0.0.pom"
    )
    central_url = (
        "https://repo1.maven.org/maven2/com/google/firebase/"
        "firebase-bom/33.0.0/firebase-bom-33.0.0.pom"
    )
    transport = _StubTransport({google_url: (404, ""), central_url: (200, _FIREBASE_POM)})
    _patch_client(monkeypatch, transport)

    bom = _bom("firebase-bom", "com.google.firebase", "firebase-bom", "33.0.0")
    [resolution] = asyncio.run(MavenBomResolver().resolve((bom,)))
    assert len(resolution.managed) == 3
    assert any("dl.google.com" in c for c in transport.calls)
    assert any("repo1.maven.org" in c for c in transport.calls)


def test_skipped_when_both_404(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = _StubTransport({})  # everything 404s
    _patch_client(monkeypatch, transport)

    bom = _bom("ghost-bom", "io.example", "ghost-bom", "1.0.0")
    result = asyncio.run(MavenBomResolver().resolve((bom,)))
    # Result is the empty tuple — failed BoMs are silently dropped, not aborted.
    assert result == ()


def test_skips_bom_without_version(monkeypatch: pytest.MonkeyPatch) -> None:
    """A BoM with no pinned version is skipped (cannot fetch its POM)."""
    transport = _StubTransport({})
    _patch_client(monkeypatch, transport)

    bom = _bom("orphan-bom", "io.example", "orphan-bom", "")
    result = asyncio.run(MavenBomResolver().resolve((bom,)))
    assert result == ()
    # No HTTP calls when version is empty
    assert transport.calls == []


def test_handles_malformed_pom_gracefully(monkeypatch: pytest.MonkeyPatch) -> None:
    pom_url = "https://repo1.maven.org/maven2/io/example/broken-bom/1.0.0/broken-bom-1.0.0.pom"
    transport = _StubTransport({pom_url: (200, "<not-real-xml")})
    _patch_client(monkeypatch, transport)

    bom = _bom("broken-bom", "io.example", "broken-bom", "1.0.0")
    result = asyncio.run(MavenBomResolver().resolve((bom,)))
    assert result == ()
