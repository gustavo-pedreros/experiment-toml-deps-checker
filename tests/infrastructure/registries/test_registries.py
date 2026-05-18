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

# RFC-0027: the publisher sets <release> to a pre-release version
# while the actual stable line continues in <versions>. Modelled on
# the live com.google.protobuf:protoc metadata as observed on
# 2026-05-17, where <release>21.0-rc-1</release> coexisted with
# a 4.x.y stable line.
_METADATA_PROTOC_SHAPE = """\
<?xml version="1.0" encoding="UTF-8"?>
<metadata>
  <groupId>com.google.protobuf</groupId>
  <artifactId>protoc</artifactId>
  <versioning>
    <latest>21.0-rc-1</latest>
    <release>21.0-rc-1</release>
    <versions>
      <version>4.29.2</version>
      <version>4.30.0</version>
      <version>4.34.0-RC1</version>
      <version>4.34.1</version>
      <version>4.35.0-RC2</version>
      <version>21.0-rc-1</version>
    </versions>
    <lastUpdated>20260506230320</lastUpdated>
  </versioning>
</metadata>
"""

# RFC-0027: every version is a pre-release (alpha/beta/RC). After
# the stability gate we must fall back to <release> rather than
# returning None, so libraries that only ever publish pre-releases
# continue to surface a usable "latest" string.
_METADATA_NO_STABLE = """\
<?xml version="1.0" encoding="UTF-8"?>
<metadata>
  <groupId>com.example</groupId>
  <artifactId>alpha-only-lib</artifactId>
  <versioning>
    <latest>1.0.0-alpha03</latest>
    <release>1.0.0-alpha03</release>
    <versions>
      <version>1.0.0-alpha01</version>
      <version>1.0.0-alpha02</version>
      <version>1.0.0-alpha03</version>
    </versions>
  </versioning>
</metadata>
"""

# RFC-0027: every version is 0.x.y (PRE_1_0 per RFC-0026). The
# stability gate skips them all; fallback returns <release>.
_METADATA_PRE_1_0_ONLY = """\
<?xml version="1.0" encoding="UTF-8"?>
<metadata>
  <groupId>com.example</groupId>
  <artifactId>young-lib</artifactId>
  <versioning>
    <release>0.6.0</release>
    <versions>
      <version>0.1.0</version>
      <version>0.5.0</version>
      <version>0.6.0</version>
    </versions>
  </versioning>
</metadata>
"""

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

    # Versions list contains "1.0.0" (stable) — stability gate scans
    # it and returns the latest stable per RFC-0027.
    assert result == MavenVersion("1.0.0")


# ---------------------------------------------------------------------------
# RFC-0027 — stability-gated <release> fallback
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cls", REGISTRY_CLASSES)
async def test_falls_back_to_versions_when_release_is_prerelease(cls: type, tmp_path: Path) -> None:
    """Live-observed protoc shape: <release> = RC, scan finds stable."""
    async with _client({"maven-metadata.xml": (200, _METADATA_PROTOC_SHAPE)}) as c:
        registry = _make(cls, c, tmp_path)
        result = await registry.get_latest("com.google.protobuf", "protoc")

    assert isinstance(result, MavenVersion)
    # Reverse document order skips 21.0-rc-1 (RC) and 4.35.0-RC2 (RC),
    # lands on 4.34.1 — the most recently published stable entry.
    assert str(result) == "4.34.1"
    assert result.stability is Stability.STABLE


@pytest.mark.parametrize("cls", REGISTRY_CLASSES)
async def test_falls_back_to_release_when_no_stable_in_versions(cls: type, tmp_path: Path) -> None:
    """Alpha-only library: preserve current behaviour, return <release>."""
    async with _client({"maven-metadata.xml": (200, _METADATA_NO_STABLE)}) as c:
        registry = _make(cls, c, tmp_path)
        result = await registry.get_latest("com.example", "alpha-only-lib")

    assert isinstance(result, MavenVersion)
    assert str(result) == "1.0.0-alpha03"
    assert result.stability is Stability.ALPHA


@pytest.mark.parametrize("cls", REGISTRY_CLASSES)
async def test_pre_1_0_only_falls_back_to_release(cls: type, tmp_path: Path) -> None:
    """PRE_1_0-only library: stability gate skips all, fallback returns <release>."""
    async with _client({"maven-metadata.xml": (200, _METADATA_PRE_1_0_ONLY)}) as c:
        registry = _make(cls, c, tmp_path)
        result = await registry.get_latest("com.example", "young-lib")

    assert isinstance(result, MavenVersion)
    # Same final string as today, just via the fallback path. Per
    # RFC-0026 this is PRE_1_0, not STABLE.
    assert str(result) == "0.6.0"
    assert result.stability is Stability.PRE_1_0


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
# RFC-0029 — negative-cache namespacing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cls", REGISTRY_CLASSES)
async def test_clear_negative_entries_purges_404s_only(cls: type, tmp_path: Path) -> None:
    """``clear_negative_entries`` removes 404 entries; positives survive."""

    call_count = {"hits": 0}

    class _MixedTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            call_count["hits"] += 1
            url = str(request.url)
            if "okhttp" in url:
                return httpx.Response(200, text=_METADATA_WITH_RELEASE)
            return httpx.Response(404)

    async with httpx.AsyncClient(transport=_MixedTransport()) as c:
        registry = _make(cls, c, tmp_path)
        # Populate one positive + one negative cache entry.
        await registry.get_latest("com.squareup.okhttp3", "okhttp")
        await registry.get_latest("com.example", "missing")
        baseline_hits = call_count["hits"]

        removed = registry.clear_negative_entries()
        assert removed == 1

        # Positive entry still served from cache.
        first = await registry.get_latest("com.squareup.okhttp3", "okhttp")
        assert first == MavenVersion("4.12.0")
        assert call_count["hits"] == baseline_hits  # no extra network call

        # Negative entry was purged → triggers a fresh HTTP call.
        second = await registry.get_latest("com.example", "missing")
        assert second is None
        assert call_count["hits"] == baseline_hits + 1


@pytest.mark.parametrize("cls", REGISTRY_CLASSES)
async def test_clear_negative_entries_returns_zero_on_clean_cache(
    cls: type, tmp_path: Path
) -> None:
    async with _client({}) as c:
        registry = _make(cls, c, tmp_path)
        assert registry.clear_negative_entries() == 0


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
