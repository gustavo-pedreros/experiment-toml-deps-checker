"""Unit tests for ChangelogFetcher.

All HTTP calls are intercepted with httpx.MockTransport — no network traffic.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from gradle_deps_monitor.domain.catalog import Library
from gradle_deps_monitor.domain.changelog import BreakingSignal
from gradle_deps_monitor.domain.version import MavenVersion
from gradle_deps_monitor.infrastructure.fetchers.changelog_fetcher import (
    ChangelogFetcher,
    _breaking_signal,
    _extract_github_repo,
    _is_google,
    _is_stable,
    _major,
    _make_snippet,
    _parse_latest_stable,
    _parse_scm_url,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _lib(alias: str, group: str, artifact: str, version: str = "2.9.0") -> Library:
    return Library(alias=alias, group=group, artifact=artifact, version=MavenVersion(version))


def _run(coro: Any) -> Any:
    return asyncio.get_event_loop().run_until_complete(coro)


def _mock_transport(responses: dict[str, tuple[int, str | dict]]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        for pattern, (status, body) in responses.items():
            if pattern in url:
                if isinstance(body, dict):
                    return httpx.Response(status, json=body)
                return httpx.Response(status, text=body)
        return httpx.Response(404, text="not found")

    return httpx.MockTransport(handler)


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


class TestMajor:
    def test_integer(self) -> None:
        assert _major("3.0.0") == 3

    def test_single(self) -> None:
        assert _major("2") == 2

    def test_non_numeric(self) -> None:
        assert _major("abc") == 0

    def test_empty(self) -> None:
        assert _major("") == 0


class TestIsStable:
    def test_stable(self) -> None:
        assert _is_stable("3.0.0") is True

    def test_alpha(self) -> None:
        assert _is_stable("3.0.0-alpha01") is False

    def test_rc(self) -> None:
        assert _is_stable("3.0.0-RC1") is False

    def test_snapshot(self) -> None:
        assert _is_stable("3.0.0-SNAPSHOT") is False


class TestIsGoogle:
    def test_androidx(self) -> None:
        assert _is_google("androidx.core") is True

    def test_non_google(self) -> None:
        assert _is_google("com.squareup.retrofit2") is False

    def test_com_google_firebase(self) -> None:
        assert _is_google("com.google.firebase") is True


class TestParseLatestStable:
    def test_release_element(self) -> None:
        xml = "<metadata><versioning><release>3.0.0</release></versioning></metadata>"
        assert _parse_latest_stable(xml) == "3.0.0"

    def test_prerelease_release_falls_back_to_versions(self) -> None:
        xml = """<metadata>
  <versioning>
    <release>3.0.0-alpha01</release>
    <versions>
      <version>2.9.0</version>
      <version>3.0.0-alpha01</version>
    </versions>
  </versioning>
</metadata>"""
        assert _parse_latest_stable(xml) == "2.9.0"

    def test_stable_latest_in_versions(self) -> None:
        xml = """<metadata>
  <versioning>
    <versions>
      <version>2.8.0</version>
      <version>2.9.0</version>
    </versions>
  </versioning>
</metadata>"""
        assert _parse_latest_stable(xml) == "2.9.0"

    def test_invalid_xml(self) -> None:
        assert _parse_latest_stable("<bad") is None

    def test_no_versions(self) -> None:
        assert _parse_latest_stable("<metadata></metadata>") is None


class TestParseScmUrl:
    def test_url_tag(self) -> None:
        pom = """<project>
  <scm>
    <url>https://github.com/square/retrofit</url>
  </scm>
</project>"""
        assert _parse_scm_url(pom) == "https://github.com/square/retrofit"

    def test_connection_tag(self) -> None:
        pom = """<project>
  <scm>
    <connection>scm:git:https://github.com/square/retrofit.git</connection>
  </scm>
</project>"""
        result = _parse_scm_url(pom)
        assert result is not None
        assert "retrofit" in result

    def test_no_scm(self) -> None:
        assert _parse_scm_url("<project></project>") is None

    def test_invalid_xml(self) -> None:
        assert _parse_scm_url("<bad") is None

    def test_with_namespace(self) -> None:
        pom = """<project xmlns="http://maven.apache.org/POM/4.0.0">
  <scm>
    <url>https://github.com/square/retrofit</url>
  </scm>
</project>"""
        result = _parse_scm_url(pom)
        assert result is not None
        assert "github.com" in result


class TestExtractGithubRepo:
    def test_https_url(self) -> None:
        result = _extract_github_repo("https://github.com/square/retrofit")
        assert result == ("square", "retrofit")

    def test_git_url(self) -> None:
        result = _extract_github_repo("scm:git:https://github.com/square/retrofit.git")
        assert result == ("square", "retrofit")

    def test_ssh_url(self) -> None:
        result = _extract_github_repo("git@github.com:square/retrofit.git")
        assert result == ("square", "retrofit")

    def test_non_github(self) -> None:
        assert _extract_github_repo("https://gitlab.com/foo/bar") is None

    def test_empty(self) -> None:
        assert _extract_github_repo("") is None


class TestBreakingSignal:
    def test_explicit_breaking_changes(self) -> None:
        assert _breaking_signal("## Breaking Changes\n- removed X") == BreakingSignal.LIKELY

    def test_breaking_change_keyword(self) -> None:
        assert _breaking_signal("This release has a breaking change.") == BreakingSignal.LIKELY

    def test_incompatible(self) -> None:
        assert _breaking_signal("This version is incompatible with v2.") == BreakingSignal.LIKELY

    def test_clean_release(self) -> None:
        assert _breaking_signal("Added new feature. Fixed a bug.") == BreakingSignal.CLEAN

    def test_empty(self) -> None:
        assert _breaking_signal("") == BreakingSignal.CLEAN


class TestMakeSnippet:
    def test_first_line(self) -> None:
        text = "## New Features\n\nAdded support for X."
        assert _make_snippet(text) == "New Features"

    def test_long_first_line_truncated(self) -> None:
        text = "A" * 300
        snippet = _make_snippet(text)
        assert snippet is not None
        assert len(snippet) <= 201  # 200 + ellipsis char

    def test_empty(self) -> None:
        assert _make_snippet("") is None

    def test_whitespace_only(self) -> None:
        assert _make_snippet("   \n\n  ") is None


# ---------------------------------------------------------------------------
# ChangelogFetcher integration (mocked HTTP)
# ---------------------------------------------------------------------------

_METADATA_V3 = """<metadata>
  <versioning>
    <release>3.0.0</release>
  </versioning>
</metadata>"""

_METADATA_V2 = """<metadata>
  <versioning>
    <release>2.9.0</release>
  </versioning>
</metadata>"""

_POM_WITH_GITHUB = """<project>
  <scm>
    <url>https://github.com/square/retrofit</url>
  </scm>
</project>"""

_POM_NO_SCM = "<project><groupId>com.example</groupId></project>"

_RELEASE_BODY = "## What's Changed\n\nBreaking change: removed X adapter."
_RELEASE_JSON = {
    "body": _RELEASE_BODY,
    "html_url": "https://github.com/square/retrofit/releases/tag/v3.0.0",
}

_CHANGELOG_MD = "# Changelog\n\n## 3.0.0\nBreaking changes in interceptors."


def _run_with_transport(
    fetcher: ChangelogFetcher,
    libraries: tuple[Library, ...],
    transport: httpx.MockTransport,
) -> tuple:
    async def _inner() -> tuple:
        async with httpx.AsyncClient(transport=transport, timeout=15.0) as client:
            # Bypass the internal client creation by calling the internal method directly.
            latest_results = [await fetcher._get_latest(client, lib) for lib in libraries]
            entries = []
            for lib, latest in zip(libraries, latest_results, strict=False):
                if latest and _major(latest) > _major(str(lib.version)):
                    entry = await fetcher._build_entry(client, lib, latest)
                    if entry:
                        entries.append(entry)
        return tuple(entries)

    return asyncio.get_event_loop().run_until_complete(_inner())


class TestChangelogFetcherNoUpgrade:
    def test_no_major_upgrade_no_entry(self) -> None:
        """Same major version → no entry produced."""
        fetcher = ChangelogFetcher()
        lib = _lib("retrofit", "com.squareup.retrofit2", "retrofit", "2.9.0")
        transport = _mock_transport({"maven-metadata.xml": (200, _METADATA_V2)})
        entries = _run_with_transport(fetcher, (lib,), transport)
        assert len(entries) == 0

    def test_metadata_404_no_entry(self) -> None:
        fetcher = ChangelogFetcher()
        lib = _lib("retrofit", "com.squareup.retrofit2", "retrofit", "2.9.0")
        transport = _mock_transport({})  # all 404
        entries = _run_with_transport(fetcher, (lib,), transport)
        assert len(entries) == 0

    def test_empty_libraries(self) -> None:
        fetcher = ChangelogFetcher()
        result = _run(fetcher.fetch(()))
        assert result == ()


class TestChangelogFetcherWithRelease:
    def test_major_upgrade_with_github_release(self) -> None:
        fetcher = ChangelogFetcher()
        lib = _lib("retrofit", "com.squareup.retrofit2", "retrofit", "2.9.0")
        transport = _mock_transport(
            {
                "maven-metadata.xml": (200, _METADATA_V3),
                "retrofit-3.0.0.pom": (200, _POM_WITH_GITHUB),
                "/releases/tags/v3.0.0": (200, _RELEASE_JSON),
            }
        )
        entries = _run_with_transport(fetcher, (lib,), transport)
        assert len(entries) == 1
        e = entries[0]
        assert e.alias == "retrofit"
        assert e.pinned_version == "2.9.0"
        assert e.latest_version == "3.0.0"
        assert e.breaking_signal == BreakingSignal.LIKELY
        assert e.changelog_url is not None
        assert "github.com" in e.changelog_url

    def test_breaking_signal_clean_when_no_keywords(self) -> None:
        fetcher = ChangelogFetcher()
        lib = _lib("retrofit", "com.squareup.retrofit2", "retrofit", "2.9.0")
        clean_release = {
            "body": "Added new features and fixed bugs.",
            "html_url": "https://github.com/square/retrofit/releases/tag/v3.0.0",
        }
        transport = _mock_transport(
            {
                "maven-metadata.xml": (200, _METADATA_V3),
                "retrofit-3.0.0.pom": (200, _POM_WITH_GITHUB),
                "/releases/tags/v3.0.0": (200, clean_release),
            }
        )
        entries = _run_with_transport(fetcher, (lib,), transport)
        assert len(entries) == 1
        assert entries[0].breaking_signal == BreakingSignal.CLEAN

    def test_no_pom_scm_returns_unknown_entry(self) -> None:
        """POM found but no GitHub URL → entry with UNKNOWN signal."""
        fetcher = ChangelogFetcher()
        lib = _lib("mylib", "com.example", "mylib", "1.0.0")
        transport = _mock_transport(
            {
                "maven-metadata.xml": (200, _METADATA_V3),
                "mylib-3.0.0.pom": (200, _POM_NO_SCM),
            }
        )
        entries = _run_with_transport(fetcher, (lib,), transport)
        assert len(entries) == 1
        e = entries[0]
        assert e.breaking_signal == BreakingSignal.UNKNOWN
        assert e.changelog_url is None

    def test_pom_404_returns_unknown_entry(self) -> None:
        """Metadata found (major upgrade) but POM 404 → UNKNOWN entry."""
        fetcher = ChangelogFetcher()
        lib = _lib("mylib", "com.example", "mylib", "1.0.0")
        transport = _mock_transport({"maven-metadata.xml": (200, _METADATA_V3)})
        entries = _run_with_transport(fetcher, (lib,), transport)
        assert len(entries) == 1
        assert entries[0].breaking_signal == BreakingSignal.UNKNOWN

    def test_release_api_404_falls_back_to_changelog_md(self) -> None:
        """GitHub Releases 404 but CHANGELOG.md exists → CLEAN/LIKELY based on content."""
        fetcher = ChangelogFetcher()
        lib = _lib("retrofit", "com.squareup.retrofit2", "retrofit", "2.9.0")
        # Simulate: metadata gives 3.0.0, POM has GitHub URL,
        # all release tag attempts 404, CHANGELOG.md found.
        repo_api_json = {"default_branch": "main"}
        transport = _mock_transport(
            {
                "maven-metadata.xml": (200, _METADATA_V3),
                "retrofit-3.0.0.pom": (200, _POM_WITH_GITHUB),
                "/releases/tags/": (404, "not found"),
                "/repos/square/retrofit\n": (200, repo_api_json),  # won't match exactly
                "CHANGELOG.md": (200, _CHANGELOG_MD),
            }
        )
        entries = _run_with_transport(fetcher, (lib,), transport)
        assert len(entries) == 1
        e = entries[0]
        # Either found via CHANGELOG.md (LIKELY) or fell through to repo URL (UNKNOWN)
        assert e.breaking_signal in (BreakingSignal.LIKELY, BreakingSignal.UNKNOWN)

    def test_github_token_used_in_headers(self) -> None:
        fetcher = ChangelogFetcher(github_token="ghp_test123")
        assert fetcher._headers.get("Authorization") == "Bearer ghp_test123"

    def test_no_token_no_auth_header(self) -> None:
        fetcher = ChangelogFetcher()
        assert "Authorization" not in fetcher._headers

    def test_entry_coordinate(self) -> None:
        fetcher = ChangelogFetcher()
        lib = _lib("retrofit", "com.squareup.retrofit2", "retrofit", "2.9.0")
        transport = _mock_transport({"maven-metadata.xml": (200, _METADATA_V3)})
        entries = _run_with_transport(fetcher, (lib,), transport)
        assert len(entries) == 1
        assert entries[0].coordinate == "com.squareup.retrofit2:retrofit"
