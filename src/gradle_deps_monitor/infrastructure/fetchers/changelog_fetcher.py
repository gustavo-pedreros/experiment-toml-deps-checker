"""ChangelogFetcher — discovers changelogs for libraries with major upgrades.

Pipeline per library
--------------------
1. Fetch ``maven-metadata.xml`` → get latest stable version.
2. Compare ``major(latest) > major(pinned)``; skip if no major upgrade.
3. Fetch the POM at the latest version → extract ``<scm><url>`` or
   ``<scm><connection>`` pointing to GitHub.
4. Try the **GitHub Releases API** for common tag patterns
   (``v{version}``, ``{version}``).
5. Fallback: fetch raw ``CHANGELOG.md`` from the repo's default branch.
6. Apply the **breaking-change heuristic** on any retrieved content.
7. Return a :class:`~...domain.changelog.ChangelogEntry`.

Google-hosted libraries (``androidx.*``, ``com.google.*``, etc.) use
Google Maven for the metadata lookup and Maven Central for the POM
(if available); others use Maven Central for both.

Credentials
-----------
A ``GITHUB_TOKEN`` (or ``GH_TOKEN``) environment variable is **optional**
but increases the GitHub API rate limit from 60 to 5 000 req/hour.  The
token is injected by the composition root at construction time.
"""

from __future__ import annotations

import asyncio
import re
import xml.etree.ElementTree as ET
from typing import Any

import httpx

from gradle_deps_monitor.domain.catalog import Library
from gradle_deps_monitor.domain.changelog import BreakingSignal, ChangelogEntry, ChangelogFetchStats
from gradle_deps_monitor.infrastructure._shared.http import HttpPolicy, make_resilient_client
from gradle_deps_monitor.infrastructure._shared.http.rate_limit import (
    is_rate_limited as _shared_is_rate_limited,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MAVEN_CENTRAL_BASE = "https://repo1.maven.org/maven2"
_GOOGLE_MAVEN_BASE = "https://dl.google.com/dl/android/maven2"
_GITHUB_API_BASE = "https://api.github.com"
_GITHUB_RAW_BASE = "https://raw.githubusercontent.com"

_HTTP_TIMEOUT = 15.0
# RFC-0030: cap concurrent requests so a catalog with 50+ major
# upgrades doesn't open 50+ simultaneous GitHub Releases API
# connections. Matches the GitHub Advisory Scanner's cap.
_MAX_CONCURRENT_REQUESTS = 20

# Characters of release-note body to scan for the breaking heuristic.
_SCAN_CHARS = 5000
# Characters kept as a human-readable snippet.
_SNIPPET_CHARS = 200

# Google-hosted group prefixes (use Google Maven for metadata).
_GOOGLE_GROUPS = frozenset(
    {
        "androidx",
        "com.android",
        "com.google.android",
        "com.google.firebase",
        "com.google.gms",
        "com.google.ar",
        "com.google.mlkit",
    }
)

# RFC-0024 PR #2: classification strings used to bucket each library's
# outcome at the end of its pipeline. The four values are mutually
# exclusive — exactly one is assigned per attempted library. The
# top-level ``fetch`` aggregates them into a :class:`ChangelogFetchStats`.
_CLASS_FETCHED = "fetched"
_CLASS_FALLBACK_URL_ONLY = "fallback_url_only"
_CLASS_RATE_LIMITED = "rate_limited"
_CLASS_UNKNOWN_NO_REPO = "unknown_no_repo"


# RFC-0030: rate-limit detection lifted to
# ``infrastructure/_shared/http/rate_limit.py``. The canonical
# definition lives there; this module re-exports under the original
# ``_is_rate_limited`` name so existing test imports
# (``from .changelog_fetcher import _is_rate_limited``) keep working.
_is_rate_limited = _shared_is_rate_limited


class _RateLimitTracker:
    """Per-library mutable flag set during one ``_build_entry`` call.

    Each HTTP response observed during the pipeline is fed through
    :meth:`observe`; if any of them was a documented rate-limit
    response, ``hit`` flips to ``True`` and the library is classified
    as ``_CLASS_RATE_LIMITED``. Cheap wrapper; one instance per
    library task.
    """

    __slots__ = ("hit",)

    def __init__(self) -> None:
        self.hit = False

    def observe(self, response: httpx.Response) -> None:
        if _is_rate_limited(response):
            self.hit = True


# Breaking-change heuristic — conservative: require explicit keywords.
_BREAKING_RE = re.compile(
    r"breaking[\s_-]?changes?"
    r"|BREAKING[\s_-]CHANGE"
    r"|\bincompatible\b"
    r"|removed.{0,40}\bapi\b"
    r"|migration.{0,20}required"
    r"|no longer support",
    re.IGNORECASE,
)

# Extract GitHub ``owner/repo`` from any URL / SCM connection form.
_GITHUB_REPO_RE = re.compile(
    r"github\.com[:/]([a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+?)(?:\.git)?(?:[/\s\"'<]|$)"
)


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------


def _group_path(group: str) -> str:
    return group.replace(".", "/")


def _is_google(group: str) -> bool:
    return any(group == g or group.startswith(g + ".") for g in _GOOGLE_GROUPS)


def _metadata_url(group: str, artifact: str) -> str:
    base = _GOOGLE_MAVEN_BASE if _is_google(group) else _MAVEN_CENTRAL_BASE
    return f"{base}/{_group_path(group)}/{artifact}/maven-metadata.xml"


def _pom_url(group: str, artifact: str, version: str) -> str:
    return (
        f"{_MAVEN_CENTRAL_BASE}/{_group_path(group)}/{artifact}/{version}/{artifact}-{version}.pom"
    )


# ---------------------------------------------------------------------------
# Version helpers
# ---------------------------------------------------------------------------


def _major(version: str) -> int:
    """Return the leading major integer of *version*, or 0 on parse failure."""
    m = re.match(r"^(\d+)", version)
    return int(m.group(1)) if m else 0


def _is_stable(version: str) -> bool:
    """Return ``True`` when *version* looks like a stable release (no pre-release label)."""
    return bool(re.match(r"^\d+(\.\d+)*$", version))


# ---------------------------------------------------------------------------
# XML / metadata parsers
# ---------------------------------------------------------------------------


def _parse_latest_stable(metadata_xml: str) -> str | None:
    """Return the latest stable version from Maven metadata XML.

    Prefers ``<release>`` if stable; otherwise scans ``<versions>`` in
    reverse order for the first stable entry.
    """
    try:
        root = ET.fromstring(metadata_xml)
    except ET.ParseError:
        return None

    release = root.findtext("versioning/release") or ""
    if release and _is_stable(release):
        return release

    versions_el = root.find("versioning/versions")
    if versions_el is None:
        return None
    versions = [v.text for v in versions_el.findall("version") if v.text]
    stable = [v for v in versions if v and _is_stable(v)]
    return stable[-1] if stable else None


def _parse_scm_url(pom_xml: str) -> str | None:
    """Extract the ``<scm><url>`` or ``<scm><connection>`` from a POM."""
    try:
        root = ET.fromstring(pom_xml)
    except ET.ParseError:
        return None

    ns = ""
    if root.tag.startswith("{"):
        ns = root.tag.split("}")[0].lstrip("{")

    def _find(tag: str) -> str | None:
        el = root.find(f"{{{ns}}}{tag}" if ns else tag)
        return el.text if el is not None else None

    scm = root.find(f"{{{ns}}}scm" if ns else "scm")
    if scm is None:
        return None

    for sub in ("url", "connection", "developerConnection"):
        el = scm.find(f"{{{ns}}}{sub}" if ns else sub)
        if el is not None and el.text:
            return el.text.strip()
    return None


def _extract_github_repo(scm_url: str) -> tuple[str, str] | None:
    """Return ``(owner, repo)`` from a GitHub SCM URL, or ``None``."""
    m = _GITHUB_REPO_RE.search(scm_url)
    if not m:
        return None
    parts = m.group(1).split("/")
    if len(parts) < 2:
        return None
    return parts[0], parts[1]


# ---------------------------------------------------------------------------
# Breaking-change heuristic
# ---------------------------------------------------------------------------


def _breaking_signal(text: str) -> BreakingSignal:
    """Apply the breaking-change heuristic to *text* (first ``_SCAN_CHARS`` chars)."""
    sample = text[:_SCAN_CHARS]
    if _BREAKING_RE.search(sample):
        return BreakingSignal.LIKELY
    return BreakingSignal.CLEAN


def _make_snippet(text: str) -> str | None:
    """Return a short human-readable excerpt, or ``None`` for empty text."""
    stripped = text.strip()
    if not stripped:
        return None
    first_line = stripped.splitlines()[0].strip("# ").strip()
    if len(first_line) > _SNIPPET_CHARS:
        return first_line[:_SNIPPET_CHARS] + "…"
    return first_line or None


# ---------------------------------------------------------------------------
# ChangelogFetcher
# ---------------------------------------------------------------------------


class ChangelogFetcher:
    """Discovers changelogs for libraries with a major version upgrade available.

    :param github_token: Optional GitHub personal access token or fine-grained
        token.  Raises the API rate limit from 60 to 5 000 req/hour.
    """

    def __init__(self, github_token: str | None = None) -> None:
        self._token = github_token

    @property
    def _headers(self) -> dict[str, str]:
        hdrs: dict[str, str] = {"Accept": "application/vnd.github+json"}
        if self._token:
            hdrs["Authorization"] = f"Bearer {self._token}"
        return hdrs

    async def fetch(
        self, libraries: tuple[Library, ...]
    ) -> tuple[tuple[ChangelogEntry, ...], ChangelogFetchStats]:
        """Return changelog entries for libraries with a major upgrade available.

        Also returns a :class:`ChangelogFetchStats` summarising the
        outcomes of every per-library pipeline run, so the presentation
        layer can surface silent degradation (notably GitHub
        rate-limiting). RFC-0024 PR #2 made the return type a tuple of
        ``(entries, stats)``; pre-PR-#2 callers receiving just
        ``entries`` need to unpack the new tuple.
        """
        if not libraries:
            return (), ChangelogFetchStats()

        # RFC-0030: resilient transport handles transient 429 / 5xx /
        # network blips. The per-library Semaphore caps concurrency for
        # both gather batches so a 170-lib catalog doesn't fan out 170
        # simultaneous Maven + GitHub requests.
        policy = HttpPolicy(timeout_seconds=_HTTP_TIMEOUT, max_concurrency=_MAX_CONCURRENT_REQUESTS)
        async with make_resilient_client(policy=policy) as client:
            sem = asyncio.Semaphore(_MAX_CONCURRENT_REQUESTS)

            async def _bounded_latest(lib: Library) -> str | None:
                async with sem:
                    return await self._get_latest(client, lib)

            # Step 1: resolve latest stable versions for all libraries in parallel.
            latest_tasks = [_bounded_latest(lib) for lib in libraries]
            latest_results: list[str | None] = list(
                await asyncio.gather(*latest_tasks, return_exceptions=False)
            )

            # Step 2: for each library with a major upgrade, build an entry.
            async def _bounded_entry(lib: Library, latest: str) -> tuple[ChangelogEntry, str]:
                async with sem:
                    return await self._build_entry(client, lib, latest)

            entry_tasks = []
            for lib, latest in zip(libraries, latest_results, strict=False):
                if latest is None:
                    continue
                if _major(latest) > _major(str(lib.version)):
                    entry_tasks.append(_bounded_entry(lib, latest))

            if not entry_tasks:
                return (), ChangelogFetchStats()

            outcomes: list[tuple[ChangelogEntry, str]] = list(
                await asyncio.gather(*entry_tasks, return_exceptions=False)
            )

        entries = tuple(entry for entry, _ in outcomes)
        stats = ChangelogFetchStats(
            attempted=len(outcomes),
            fetched=sum(1 for _, c in outcomes if c == _CLASS_FETCHED),
            fallback_url_only=sum(1 for _, c in outcomes if c == _CLASS_FALLBACK_URL_ONLY),
            rate_limited=sum(1 for _, c in outcomes if c == _CLASS_RATE_LIMITED),
            unknown_no_repo=sum(1 for _, c in outcomes if c == _CLASS_UNKNOWN_NO_REPO),
        )
        return entries, stats

    # ------------------------------------------------------------------
    # Step 1: latest version lookup
    # ------------------------------------------------------------------

    async def _get_latest(self, client: httpx.AsyncClient, lib: Library) -> str | None:
        url = _metadata_url(lib.group, lib.artifact)
        try:
            resp = await client.get(url)
        except httpx.HTTPError:
            return None
        if resp.status_code != 200:
            return None
        return _parse_latest_stable(resp.text)

    # ------------------------------------------------------------------
    # Steps 2-6: build a ChangelogEntry for one library
    # ------------------------------------------------------------------

    async def _build_entry(
        self, client: httpx.AsyncClient, lib: Library, latest: str
    ) -> tuple[ChangelogEntry, str]:
        """Build one entry + its outcome classification.

        Returns ``(entry, classification)`` where ``classification`` is
        one of the ``_CLASS_*`` constants. The classification is the
        worst observed outcome along the pipeline: if any HTTP response
        was a documented rate-limit hit, the library is classified as
        rate-limited even if a later fallback succeeded. This matches
        the user-felt symptom — once rate-limited, the report quality
        is suspect.
        """
        coordinate = f"{lib.group}:{lib.artifact}"
        tracker = _RateLimitTracker()

        # Step 3: fetch POM → SCM URL → GitHub repo
        github_repo = await self._get_github_repo(client, lib, latest, tracker)

        if github_repo is None:
            # No GitHub repo found — return entry with UNKNOWN signal.
            entry = ChangelogEntry(
                alias=lib.alias,
                coordinate=coordinate,
                pinned_version=str(lib.version),
                latest_version=latest,
            )
            classification = _CLASS_RATE_LIMITED if tracker.hit else _CLASS_UNKNOWN_NO_REPO
            return entry, classification

        owner, repo = github_repo

        # Step 4: try GitHub Releases API
        release_body, release_url = await self._fetch_github_release(
            client, owner, repo, latest, tracker
        )

        if release_body is not None and release_url is not None:
            entry = ChangelogEntry(
                alias=lib.alias,
                coordinate=coordinate,
                pinned_version=str(lib.version),
                latest_version=latest,
                changelog_url=release_url,
                breaking_signal=_breaking_signal(release_body),
                snippet=_make_snippet(release_body),
            )
            # Even a "successful" fetch can have been preceded by a
            # rate-limited response on another tag pattern; prefer the
            # degraded classification so the warning surfaces.
            classification = _CLASS_RATE_LIMITED if tracker.hit else _CLASS_FETCHED
            return entry, classification

        # Step 5: fallback — CHANGELOG.md at repo root
        changelog_body, changelog_url = await self._fetch_changelog_md(client, owner, repo, tracker)

        if changelog_body is not None and changelog_url is not None:
            entry = ChangelogEntry(
                alias=lib.alias,
                coordinate=coordinate,
                pinned_version=str(lib.version),
                latest_version=latest,
                changelog_url=changelog_url,
                breaking_signal=_breaking_signal(changelog_body),
                snippet=_make_snippet(changelog_body),
            )
            classification = _CLASS_RATE_LIMITED if tracker.hit else _CLASS_FETCHED
            return entry, classification

        # GitHub repo found but no release notes retrieved.
        repo_url = f"https://github.com/{owner}/{repo}"
        entry = ChangelogEntry(
            alias=lib.alias,
            coordinate=coordinate,
            pinned_version=str(lib.version),
            latest_version=latest,
            changelog_url=repo_url,
        )
        classification = _CLASS_RATE_LIMITED if tracker.hit else _CLASS_FALLBACK_URL_ONLY
        return entry, classification

    async def _get_github_repo(
        self,
        client: httpx.AsyncClient,
        lib: Library,
        latest: str,
        tracker: _RateLimitTracker | None = None,
    ) -> tuple[str, str] | None:
        url = _pom_url(lib.group, lib.artifact, latest)
        try:
            resp = await client.get(url)
        except httpx.HTTPError:
            return None
        if tracker is not None:
            tracker.observe(resp)
        if resp.status_code != 200:
            return None
        scm = _parse_scm_url(resp.text)
        if scm is None:
            return None
        return _extract_github_repo(scm)

    async def _fetch_github_release(
        self,
        client: httpx.AsyncClient,
        owner: str,
        repo: str,
        version: str,
        tracker: _RateLimitTracker | None = None,
    ) -> tuple[str | None, str | None]:
        """Try common tag patterns and return ``(body, html_url)`` or ``(None, None)``."""
        for tag in (f"v{version}", version, f"release-{version}", f"{repo}-{version}"):
            url = f"{_GITHUB_API_BASE}/repos/{owner}/{repo}/releases/tags/{tag}"
            try:
                resp = await client.get(url, headers=self._headers)
            except httpx.HTTPError:
                continue
            if tracker is not None:
                tracker.observe(resp)
            if resp.status_code == 200:
                data: dict[str, Any] = resp.json()
                body = data.get("body") or ""
                html_url = data.get("html_url") or ""
                if html_url:
                    return body, html_url
        return None, None

    async def _fetch_changelog_md(
        self,
        client: httpx.AsyncClient,
        owner: str,
        repo: str,
        tracker: _RateLimitTracker | None = None,
    ) -> tuple[str | None, str | None]:
        """Fetch CHANGELOG.md from the default branch. Returns ``(content, url)``."""
        # Resolve default branch
        api_url = f"{_GITHUB_API_BASE}/repos/{owner}/{repo}"
        branch = "main"
        try:
            resp = await client.get(api_url, headers=self._headers)
            if tracker is not None:
                tracker.observe(resp)
            if resp.status_code == 200:
                branch = resp.json().get("default_branch", "main")
        except httpx.HTTPError:
            pass

        for filename in ("CHANGELOG.md", "CHANGES.md", "CHANGELOG"):
            raw_url = f"{_GITHUB_RAW_BASE}/{owner}/{repo}/{branch}/{filename}"
            try:
                resp = await client.get(raw_url)
            except httpx.HTTPError:
                continue
            if tracker is not None:
                tracker.observe(resp)
            if resp.status_code == 200 and resp.text.strip():
                html_url = f"https://github.com/{owner}/{repo}/blob/{branch}/{filename}"
                return resp.text, html_url

        return None, None
