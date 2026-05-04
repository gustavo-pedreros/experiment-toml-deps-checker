"""Tests for MavenCentralRegistry and GoogleMavenRegistry.

No real HTTP calls — a custom httpx transport intercepts all requests.
diskcache uses a tmp_path directory so the cache is fresh per test.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import httpx
import pytest

from gradle_deps_monitor.application.ports.version_registry import VersionRegistryError
from gradle_deps_monitor.domain.version import MavenVersion, Stability
from gradle_deps_monitor.infrastructure.registries.google_maven import GoogleMavenRegistry
from gradle_deps_monitor.infrastructure.registries.maven_central import MavenCentralRegistry

# ---------------------------------------------------------------------------
# XML fixtures
# ---------------------------------------------------------------------------

_METADATA_WITH_RELEASE = """\
<?xml version="1.0" encoding="UTF-8"?>
<metadata>
  <groupId>com.squareup.okhttp3</groupId>
  <artifactId>okhttp</artifactId>
  <versioning>
    <latest>5.0.0-alpha.14</latest>
    <release>4.12.0</release>
    <versions>
      <version>4.11.0</version>
      <version>4.12.0</version>
      <version>5.0.0-alpha.14</version>
    </versions>
    <lastUpdated>20240601000000</lastUpdated>
  </versioning>
</metadata>
"""

_METADATA_WITHOUT_RELEASE = """\
<?xml version="1.0" encoding="UTF-8"?>
<metadata>
  <groupId>com.example</groupId>
  <artifactId>lib</artifactId>
  <versioning>
    <versions>
      <version>1.0.0</version>
    </versions>
  </versioning>
</metadata>
"""

_METADATA_BAD_XML = "this is not xml <<<"

# ---------------------------------------------------------------------------
# Transport helpers
# ---------------------------------------------------------------------------

Handler = Callable[[httpx.Request], httpx.Response]


class _Transport(httpx.AsyncBaseTransport):
    """Routes requests to a per-URL-substring handler map."""

    def __init__(self, routes: dict[str, tuple[int, str]]) -> None:
        self._routes = routes

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        for pattern, (status, body) in self._routes.items():
            if pattern in url:
                return httpx.Response(status, text=body)
        return httpx.Response(404)


class _ErrorTransport(httpx.AsyncBaseTransport):
    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("simulated connection refused")


def _client(routes: dict[str, tuple[int, str]]) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=_Transport(routes))


def _error_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=_ErrorTransport())


# ---------------------------------------------------------------------------
# Parametrised registry factory
# ---------------------------------------------------------------------------

REGISTRY_CLASSES = [MavenCentralRegistry, GoogleMavenRegistry]


def _make(cls: type, client: httpx.AsyncClient, cache_dir: Path):  # type: ignore[no-untyped-def]
    return cls(client=client, cache_dir=cache_dir)


# ---------------------------------------------------------------------------
# Happy path — both registries behave identically
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cls", REGISTRY_CLASSES)
async def test_returns_release_version(cls: type, tmp_path: Path) -> None:
    async with _client({"maven-metadata.xml": (200, _METADATA_WITH_RELEASE)}) as c:
        registry = _make(cls, c, tmp_path)
        result = await registry.get_latest("com.squareup.okhttp3", "okhttp")

    assert isinstance(result, MavenVersion)
    assert str(result) == "4.12.0"
    assert result.stability is Stability.STABLE


@pytest.mark.parametrize("cls", REGISTRY_CLASSES)
async def test_returns_none_for_404(cls: type, tmp_path: Path) -> None:
    async with _client({}) as c:  # no routes → all 404
        registry = _make(cls, c, tmp_path)
        result = await registry.get_latest("com.example", "missing")

    assert result is None


@pytest.mark.parametrize("cls", REGISTRY_CLASSES)
async def test_returns_none_when_no_release_tag(cls: type, tmp_path: Path) -> None:
    async with _client({"maven-metadata.xml": (200, _METADATA_WITHOUT_RELEASE)}) as c:
        registry = _make(cls, c, tmp_path)
        result = await registry.get_latest("com.example", "lib")

    assert result is None


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cls", REGISTRY_CLASSES)
async def test_raises_on_network_error(cls: type, tmp_path: Path) -> None:
    async with _error_client() as c:
        registry = _make(cls, c, tmp_path)
        with pytest.raises(VersionRegistryError, match="Network error"):
            await registry.get_latest("com.example", "lib")


@pytest.mark.parametrize("cls", REGISTRY_CLASSES)
async def test_raises_on_bad_xml(cls: type, tmp_path: Path) -> None:
    async with _client({"maven-metadata.xml": (200, _METADATA_BAD_XML)}) as c:
        registry = _make(cls, c, tmp_path)
        with pytest.raises(VersionRegistryError, match="XML parse error"):
            await registry.get_latest("com.example", "lib")


@pytest.mark.parametrize("cls", REGISTRY_CLASSES)
async def test_raises_on_unexpected_status(cls: type, tmp_path: Path) -> None:
    async with _client({"maven-metadata.xml": (500, "Internal Server Error")}) as c:
        registry = _make(cls, c, tmp_path)
        with pytest.raises(VersionRegistryError, match="HTTP 500"):
            await registry.get_latest("com.example", "lib")


# ---------------------------------------------------------------------------
# Cache behaviour
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cls", REGISTRY_CLASSES)
async def test_cache_hit_skips_network(cls: type, tmp_path: Path) -> None:
    call_count = 0

    class _CountingTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            return httpx.Response(200, text=_METADATA_WITH_RELEASE)

    async with httpx.AsyncClient(transport=_CountingTransport()) as c:
        registry = _make(cls, c, tmp_path)
        first = await registry.get_latest("com.squareup.okhttp3", "okhttp")
        second = await registry.get_latest("com.squareup.okhttp3", "okhttp")

    assert first == second == MavenVersion("4.12.0")
    assert call_count == 1  # second call served from cache


@pytest.mark.parametrize("cls", REGISTRY_CLASSES)
async def test_cache_stores_not_found(cls: type, tmp_path: Path) -> None:
    call_count = 0

    class _CountingTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            return httpx.Response(404)

    async with httpx.AsyncClient(transport=_CountingTransport()) as c:
        registry = _make(cls, c, tmp_path)
        await registry.get_latest("com.example", "missing")
        await registry.get_latest("com.example", "missing")

    assert call_count == 1  # 404 also cached


# ---------------------------------------------------------------------------
# URL construction
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("group", "artifact", "expected_fragment"),
    [
        ("com.squareup.okhttp3", "okhttp", "com/squareup/okhttp3/okhttp/maven-metadata.xml"),
        ("androidx.compose.ui", "ui", "androidx/compose/ui/ui/maven-metadata.xml"),
    ],
)
async def test_maven_central_url_construction(
    group: str,
    artifact: str,
    expected_fragment: str,
    tmp_path: Path,
) -> None:
    captured: list[str] = []

    class _CaptureTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            captured.append(str(request.url))
            return httpx.Response(404)

    async with httpx.AsyncClient(transport=_CaptureTransport()) as c:
        registry = MavenCentralRegistry(client=c, cache_dir=tmp_path)
        await registry.get_latest(group, artifact)

    assert captured and expected_fragment in captured[0]
