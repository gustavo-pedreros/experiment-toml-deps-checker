"""PomLicenseChecker — extracts license metadata from Maven POM files.

For each library in the version catalog the checker:

1. Fetches ``{artifact}-{version}.pom`` from Maven Central (primary).
2. Falls back to Google Maven for libraries in well-known Google groups.
3. Parses the ``<licenses><license>`` block.
4. Classifies the license text into a :class:`~...domain.license.LicenseTier`.

Only non-permissive findings (WEAK_COPYLEFT, STRONG_COPYLEFT, UNKNOWN) are
included in the returned :class:`~...domain.license.LicenseAudit`.

Classification relies on keyword matching against a curated list.  LGPL
keywords are checked *before* GPL to avoid false-positive STRONG_COPYLEFT
classification of LGPL-licensed libraries.
"""

from __future__ import annotations

import asyncio
import xml.etree.ElementTree as ET

import httpx

from gradle_deps_monitor.domain.catalog import Library
from gradle_deps_monitor.domain.license import LicenseAudit, LicenseFinding, LicenseTier

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MAVEN_CENTRAL_BASE = "https://repo1.maven.org/maven2"
_GOOGLE_MAVEN_BASE = "https://dl.google.com/dl/android/maven2"

# HTTP request timeout (seconds).
_HTTP_TIMEOUT = 15.0

# Groups that are likely hosted on Google Maven rather than Maven Central.
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

# ---------------------------------------------------------------------------
# License keyword lists
# Order matters: LGPL must appear before GPL so that LGPL is not misclassified
# as STRONG_COPYLEFT. Similarly EUPL is checked before GPL.
# ---------------------------------------------------------------------------

# Weak copyleft: linking is generally permitted; modifications must be shared.
_WEAK_COPYLEFT_KEYWORDS: tuple[str, ...] = (
    "lgpl",
    "lesser gpl",
    "lesser general public",
    "mozilla public",
    "mpl-",
    "eclipse public",
    "epl-",
    "cddl",
    "common development and distribution",
    "eupl",
    "european union public",
)

# Strong copyleft: typically incompatible with closed-source distribution.
_STRONG_COPYLEFT_KEYWORDS: tuple[str, ...] = (
    "agpl",
    "affero",
    "sspl",
    "server side public",
    "gpl",  # must come after lgpl/eupl checks
    "general public license",  # ditto
)

# Permissive: no restrictions on use in closed-source projects.
_PERMISSIVE_KEYWORDS: tuple[str, ...] = (
    "apache",
    "mit license",
    " mit ",
    "bsd",
    "isc",
    "unlicense",
    "cc0",
    "public domain",
    "boost software",
    "zlib",
    "wtfpl",
    "do what the fuck",
)


# ---------------------------------------------------------------------------
# Pure helpers (importable for tests)
# ---------------------------------------------------------------------------


def _group_path(group: str) -> str:
    """Convert Maven group ID to URL path segment."""
    return group.replace(".", "/")


def _pom_url(base: str, group: str, artifact: str, version: str) -> str:
    return f"{base}/{_group_path(group)}/{artifact}/{version}/{artifact}-{version}.pom"


def _is_google_library(group: str) -> bool:
    """Return ``True`` for groups hosted on Google Maven."""
    return any(group == g or group.startswith(g + ".") for g in _GOOGLE_GROUPS)


def _classify_license(license_name: str | None, license_url: str | None) -> LicenseTier:
    """Classify a license into a :class:`~...domain.license.LicenseTier`.

    The classification is keyword-based against the concatenation of *name*
    and *url* (both lowercased).  When neither value is provided the result
    is :attr:`~...domain.license.LicenseTier.UNKNOWN`.

    Keyword order matters — ``lgpl`` is checked before ``gpl`` so that LGPL
    licenses are not promoted to STRONG_COPYLEFT.
    """
    text = f"{license_name or ''} {license_url or ''}".lower()
    if not text.strip():
        return LicenseTier.UNKNOWN

    if any(kw in text for kw in _WEAK_COPYLEFT_KEYWORDS):
        return LicenseTier.WEAK_COPYLEFT

    if any(kw in text for kw in _STRONG_COPYLEFT_KEYWORDS):
        return LicenseTier.STRONG_COPYLEFT

    if any(kw in text for kw in _PERMISSIVE_KEYWORDS):
        return LicenseTier.PERMISSIVE

    return LicenseTier.UNKNOWN


def _parse_license_elements(pom_text: str) -> list[tuple[str | None, str | None]]:
    """Extract ``(name, url)`` pairs from a POM XML string.

    Returns an empty list when the POM has no ``<licenses>`` block or when
    the XML cannot be parsed.
    """
    try:
        root = ET.fromstring(pom_text)
    except ET.ParseError:
        return []

    # Maven POMs often carry a default namespace — strip it for simple XPath.
    ns = ""
    if root.tag.startswith("{"):
        ns = root.tag.split("}")[0].lstrip("{")

    def _tag(local: str) -> str:
        return f"{{{ns}}}{local}" if ns else local

    licenses_el = root.find(_tag("licenses"))
    if licenses_el is None:
        return []

    result: list[tuple[str | None, str | None]] = []
    for lic in licenses_el.findall(_tag("license")):
        name_el = lic.find(_tag("name"))
        url_el = lic.find(_tag("url"))
        name = name_el.text.strip() if name_el is not None and name_el.text else None
        url = url_el.text.strip() if url_el is not None and url_el.text else None
        result.append((name, url))
    return result


# ---------------------------------------------------------------------------
# Checker
# ---------------------------------------------------------------------------


class PomLicenseChecker:
    """Checks library licenses by parsing Maven POM ``<licenses>`` blocks.

    All HTTP requests are made concurrently via :func:`asyncio.gather`.
    The checker first tries Maven Central; for Google-group libraries it
    falls back to Google Maven when Maven Central returns a non-200 status.

    :param http_timeout: Per-request timeout in seconds (default: 15).
    """

    def __init__(self, http_timeout: float = _HTTP_TIMEOUT) -> None:
        self._timeout = http_timeout

    async def check(self, libraries: tuple[Library, ...]) -> LicenseAudit:
        """Audit *libraries* and return a :class:`~...domain.license.LicenseAudit`.

        :param libraries: All catalog libraries to classify.
        :returns: Audit containing only non-permissive findings.
        """
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            tasks = [self._check_library(client, lib) for lib in libraries]
            all_findings: list[LicenseFinding] = list(await asyncio.gather(*tasks))

        flagged = [f for f in all_findings if f.tier != LicenseTier.PERMISSIVE]
        flagged.sort(key=lambda f: (f.tier.value, f.alias))

        return LicenseAudit(
            findings=tuple(flagged),
            libraries_audited=len(libraries),
        )

    async def _check_library(self, client: httpx.AsyncClient, lib: Library) -> LicenseFinding:
        """Fetch and classify the license for a single *lib*."""
        pom_text = await self._fetch_pom(client, lib)

        coordinate = f"{lib.group}:{lib.artifact}"
        version = str(lib.version)

        if pom_text is None:
            return LicenseFinding(
                alias=lib.alias,
                coordinate=coordinate,
                version=version,
                license_name=None,
                license_url=None,
                tier=LicenseTier.UNKNOWN,
            )

        license_elements = _parse_license_elements(pom_text)
        if not license_elements:
            return LicenseFinding(
                alias=lib.alias,
                coordinate=coordinate,
                version=version,
                license_name=None,
                license_url=None,
                tier=LicenseTier.UNKNOWN,
            )

        # Use the first declared license (most POMs declare exactly one).
        name, url = license_elements[0]
        tier = _classify_license(name, url)

        return LicenseFinding(
            alias=lib.alias,
            coordinate=coordinate,
            version=version,
            license_name=name,
            license_url=url,
            tier=tier,
        )

    async def _fetch_pom(self, client: httpx.AsyncClient, lib: Library) -> str | None:
        """Fetch the POM for *lib*'s pinned version.

        Tries Maven Central first; for Google-group libraries falls back to
        Google Maven when Maven Central returns a non-200 response.
        Returns the POM XML text, or ``None`` on failure.
        """
        group, artifact, version = lib.group, lib.artifact, str(lib.version)

        try:
            resp = await client.get(_pom_url(_MAVEN_CENTRAL_BASE, group, artifact, version))
        except httpx.HTTPError:
            resp = None

        if resp is not None and resp.status_code == 200:
            return resp.text

        # Fallback: Google Maven for known Google-hosted libraries.
        if _is_google_library(group):
            try:
                g_resp = await client.get(_pom_url(_GOOGLE_MAVEN_BASE, group, artifact, version))
                if g_resp.status_code == 200:
                    return g_resp.text
            except httpx.HTTPError:
                pass

        return None


# Expose helpers under a private alias for backward-compat with test imports.
_parse_licenses = _parse_license_elements
_classify = _classify_license


def _make_pom_xml(
    *,
    license_name: str | None = None,
    license_url: str | None = None,
    with_namespace: bool = False,
    has_licenses_block: bool = True,
) -> str:
    """Build a minimal POM XML string for use in tests."""
    ns_attr = ' xmlns="http://maven.apache.org/POM/4.0.0"' if with_namespace else ""
    if not has_licenses_block:
        return f"<project{ns_attr}><groupId>com.example</groupId></project>"
    name_el = f"<name>{license_name}</name>" if license_name else ""
    url_el = f"<url>{license_url}</url>" if license_url else ""
    return f"<project{ns_attr}><licenses><license>{name_el}{url_el}</license></licenses></project>"
