"""LibraryHealthChecker — detects deprecated, relocated, and inactive libraries."""

from __future__ import annotations

import asyncio
import xml.etree.ElementTree as ET
from datetime import date, datetime
from importlib import resources
from typing import Any

import httpx
import yaml

from gradle_deps_monitor.domain.catalog import Library
from gradle_deps_monitor.domain.library_health import (
    HealthSignal,
    LibraryHealthFinding,
    LibraryHealthSeverity,
)
from gradle_deps_monitor.infrastructure._shared.http import HttpPolicy, make_resilient_client

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MAVEN_CENTRAL_BASE = "https://repo1.maven.org/maven2"

# Inactivity thresholds (days since last Maven release).
_INACTIVE_DAYS = 730  # 24 months → MEDIUM
_ABANDONED_DAYS = 1095  # 36 months → HIGH

# RFC-0030: cap concurrent per-library Maven-metadata + POM requests
# during ``_run_http_checks`` so a 170-library catalog doesn't open
# 170 simultaneous connections to Maven Central.
_MAX_CONCURRENT_REQUESTS = 20

# Groups published exclusively on Google Maven — skip inactivity check.
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

# Group prefixes for "stable by design" specifications whose reference
# implementations are intentionally frozen and won't see new releases.
# Skip the inactivity heuristic for these — a 5780-day-old artifact
# under ``javax.inject`` is a feature of the JSR, not abandonment.
# Issue #10 from the 2026-05 stress test menu.
_STABLE_BY_DESIGN_GROUPS = frozenset(
    {
        "javax",  # all of javax.* — JSR specs (e.g. JSR-330 javax.inject)
        "jakarta",  # Jakarta EE namespace successor to javax (also frozen-by-spec)
    }
)

# ---------------------------------------------------------------------------
# KB loading
# ---------------------------------------------------------------------------


def _load_kb() -> list[dict[str, Any]]:
    """Load the bundled library health knowledge base."""
    pkg = resources.files("gradle_deps_monitor.data")
    text = (pkg / "library_health_kb.yaml").read_text(encoding="utf-8")
    data: dict[str, Any] = yaml.safe_load(text)
    result: list[dict[str, Any]] = data.get("deprecated_libraries", [])
    return result


# ---------------------------------------------------------------------------
# Maven URL helpers
# ---------------------------------------------------------------------------


def _group_path(group: str) -> str:
    return group.replace(".", "/")


def _pom_url(group: str, artifact: str, version: str) -> str:
    return (
        f"{_MAVEN_CENTRAL_BASE}/{_group_path(group)}/{artifact}/{version}/{artifact}-{version}.pom"
    )


def _metadata_url(group: str, artifact: str) -> str:
    return f"{_MAVEN_CENTRAL_BASE}/{_group_path(group)}/{artifact}/maven-metadata.xml"


def _is_google_library(group: str) -> bool:
    """Return ``True`` for libraries hosted exclusively on Google Maven."""
    return any(group == g or group.startswith(g + ".") for g in _GOOGLE_GROUPS)


def _is_stable_by_design(group: str) -> bool:
    """Return ``True`` for "spec-frozen" libraries that shouldn't trigger
    the inactivity heuristic.

    JSR / Jakarta EE reference implementations (e.g. ``javax.inject``)
    are intentionally frozen — their lack of recent releases is a
    feature, not abandonment.
    """
    return any(group == g or group.startswith(g + ".") for g in _STABLE_BY_DESIGN_GROUPS)


# ---------------------------------------------------------------------------
# XML parsing helpers
# ---------------------------------------------------------------------------


def _parse_relocation(pom_text: str) -> dict[str, str] | None:
    """Extract ``<relocation>`` data from a POM XML string.

    Returns a dict with keys ``"groupId"``, ``"artifactId"``, and
    ``"message"`` (all optional), or ``None`` when no relocation is present.
    """
    try:
        root = ET.fromstring(pom_text)
    except ET.ParseError:
        return None

    # Strip the default Maven namespace so XPath works without it.
    ns = ""
    if root.tag.startswith("{"):
        ns = root.tag.split("}")[0].lstrip("{")

    def _find(el: ET.Element, tag: str) -> str | None:
        child = el.find(f"{{{ns}}}{tag}" if ns else tag)
        return child.text if child is not None else None

    dm = root.find(f"{{{ns}}}distributionManagement" if ns else "distributionManagement")
    if dm is None:
        return None
    rel = dm.find(f"{{{ns}}}relocation" if ns else "relocation")
    if rel is None:
        return None

    result: dict[str, str] = {}
    for field in ("groupId", "artifactId", "message"):
        val = _find(rel, field)
        if val:
            result[field] = val.strip()
    return result


def _parse_last_updated(metadata_text: str) -> date | None:
    """Extract the ``<lastUpdated>`` date from Maven metadata XML.

    Returns a :class:`date` or ``None`` on parse failure.
    The raw value is a 14-digit string ``YYYYMMDDHHmmss``.
    """
    try:
        root = ET.fromstring(metadata_text)
    except ET.ParseError:
        return None

    ns = ""
    if root.tag.startswith("{"):
        ns = root.tag.split("}")[0].lstrip("{")

    versioning = root.find(f"{{{ns}}}versioning" if ns else "versioning")
    if versioning is None:
        return None
    lu_el = versioning.find(f"{{{ns}}}lastUpdated" if ns else "lastUpdated")
    if lu_el is None or not lu_el.text:
        return None
    raw = lu_el.text.strip()
    if len(raw) < 8:
        return None
    try:
        return datetime.strptime(raw[:8], "%Y%m%d").date()
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Checker
# ---------------------------------------------------------------------------


class LibraryHealthChecker:
    """Combines three signals to detect deprecated, relocated, and inactive libraries.

    Signal pipeline (in priority order):

    1. **Curated KB** (sync) — bundled YAML with well-known Android deprecations.
       Libraries matched here are *not* checked via HTTP.
    2. **POM relocation** (async HTTP) — fetches the Maven POM and looks for a
       ``<relocation>`` tag.  Only run for libraries not already in the curated KB.
    3. **Inactivity heuristic** (async HTTP) — fetches ``maven-metadata.xml`` and
       checks ``<lastUpdated>`` against configurable thresholds.

    :param reference_date: Date used for inactivity calculations.  Defaults to
        today; override in tests for deterministic output.
    """

    def __init__(self, reference_date: date | None = None) -> None:
        self._today = reference_date or date.today()
        self._kb: list[dict[str, Any]] = _load_kb()
        # Index curated entries by coordinate for O(1) lookup.
        self._kb_index: dict[str, dict[str, Any]] = {
            entry["coordinate"]: entry for entry in self._kb
        }

    async def check(self, libraries: tuple[Library, ...]) -> tuple[LibraryHealthFinding, ...]:
        """Return health findings for *libraries*."""
        findings: list[LibraryHealthFinding] = []
        unchecked: list[Library] = []

        # --- Signal 1: Curated KB (sync) ---
        curated_aliases: set[str] = set()
        for lib in libraries:
            coordinate = f"{lib.group}:{lib.artifact}"
            entry = self._kb_index.get(coordinate)
            if entry:
                findings.append(self._curated_finding(lib, entry))
                curated_aliases.add(lib.alias)

        # Libraries not matched by KB → queue for HTTP checks.
        unchecked = [lib for lib in libraries if lib.alias not in curated_aliases]

        if unchecked:
            # RFC-0030: resilient transport adds retry/backoff;
            # ``_run_http_checks`` caps concurrency to
            # ``_MAX_CONCURRENT_REQUESTS`` via Semaphore.
            # RFC-0030: 15 s tolerates Maven Central tail latency on
            # POM + maven-metadata.xml fetches.
            policy = HttpPolicy(timeout_seconds=15.0, max_concurrency=_MAX_CONCURRENT_REQUESTS)
            async with make_resilient_client(policy=policy) as client:
                http_findings = await self._run_http_checks(client, unchecked)
                findings.extend(http_findings)

        return tuple(findings)

    # ------------------------------------------------------------------
    # Signal 1: Curated KB
    # ------------------------------------------------------------------

    def _curated_finding(self, lib: Library, entry: dict[str, Any]) -> LibraryHealthFinding:
        severity_str: str = entry.get("severity", "high")
        severity = (
            LibraryHealthSeverity.HIGH if severity_str == "high" else LibraryHealthSeverity.MEDIUM
        )
        return LibraryHealthFinding(
            alias=lib.alias,
            coordinate=f"{lib.group}:{lib.artifact}",
            version=str(lib.version),
            signal=HealthSignal.CURATED,
            severity=severity,
            message=entry.get("reason", "Deprecated — see migration guide."),
            replacement=entry.get("replacement") or None,
            migration_url=entry.get("migration_url") or None,
        )

    # ------------------------------------------------------------------
    # Signal 2 + 3: HTTP checks (POM relocation + inactivity)
    # ------------------------------------------------------------------

    async def _run_http_checks(
        self, client: httpx.AsyncClient, libraries: list[Library]
    ) -> list[LibraryHealthFinding]:
        # RFC-0030: cap per-library concurrency. Maven Central tolerates
        # bursts but a 170-library catalog would otherwise open 170
        # simultaneous connections.
        sem = asyncio.Semaphore(_MAX_CONCURRENT_REQUESTS)

        async def _one(lib: Library) -> LibraryHealthFinding | None:
            async with sem:
                return await self._check_library(client, lib)

        results: list[LibraryHealthFinding | None] = await asyncio.gather(
            *(_one(lib) for lib in libraries)
        )
        return [f for f in results if f is not None]

    async def _check_library(
        self, client: httpx.AsyncClient, lib: Library
    ) -> LibraryHealthFinding | None:
        """Run POM relocation + inactivity checks for a single library.

        POM relocation is checked first; if found, the inactivity check is skipped.
        """
        # --- POM relocation check ---
        relocation = await self._fetch_relocation(client, lib)
        if relocation is not None:
            new_group = relocation.get("groupId", "")
            new_artifact = relocation.get("artifactId", "")
            replacement = f"{new_group}:{new_artifact}" if new_group or new_artifact else None
            msg_parts = [relocation.get("message", "").strip()]
            coordinate = f"{lib.group}:{lib.artifact}"
            message = (
                f"{coordinate} has been relocated on Maven Central."
                if not msg_parts[0]
                else msg_parts[0]
            )
            return LibraryHealthFinding(
                alias=lib.alias,
                coordinate=coordinate,
                version=str(lib.version),
                signal=HealthSignal.RELOCATED,
                severity=LibraryHealthSeverity.HIGH,
                message=message,
                replacement=replacement,
            )

        # --- Inactivity check ---
        # Skip Google-hosted libraries (no maven-metadata.xml on Maven
        # Central) and spec-frozen libraries (``javax.*`` / ``jakarta.*``
        # — JSR reference implementations are intentionally inactive).
        if _is_google_library(lib.group) or _is_stable_by_design(lib.group):
            return None
        return await self._fetch_inactivity(client, lib)

    async def _fetch_relocation(
        self, client: httpx.AsyncClient, lib: Library
    ) -> dict[str, str] | None:
        url = _pom_url(lib.group, lib.artifact, str(lib.version))
        try:
            resp = await client.get(url)
        except httpx.HTTPError:
            return None
        if resp.status_code != 200:
            return None
        return _parse_relocation(resp.text)

    async def _fetch_inactivity(
        self, client: httpx.AsyncClient, lib: Library
    ) -> LibraryHealthFinding | None:
        url = _metadata_url(lib.group, lib.artifact)
        try:
            resp = await client.get(url)
        except httpx.HTTPError:
            return None
        if resp.status_code != 200:
            return None

        last_updated = _parse_last_updated(resp.text)
        if last_updated is None:
            return None

        days = (self._today - last_updated).days
        if days < _INACTIVE_DAYS:
            return None

        coordinate = f"{lib.group}:{lib.artifact}"
        if days >= _ABANDONED_DAYS:
            return LibraryHealthFinding(
                alias=lib.alias,
                coordinate=coordinate,
                version=str(lib.version),
                signal=HealthSignal.INACTIVE,
                severity=LibraryHealthSeverity.HIGH,
                message=(
                    f"{coordinate} has had no Maven release in {days} days "
                    f"({days // 365} years) — likely abandoned."
                ),
                days_since_release=days,
            )
        return LibraryHealthFinding(
            alias=lib.alias,
            coordinate=coordinate,
            version=str(lib.version),
            signal=HealthSignal.INACTIVE,
            severity=LibraryHealthSeverity.MEDIUM,
            message=(
                f"{coordinate} has had no Maven release in {days} days "
                f"({days // 12 // 30} months) — inactive."
            ),
            days_since_release=days,
        )
