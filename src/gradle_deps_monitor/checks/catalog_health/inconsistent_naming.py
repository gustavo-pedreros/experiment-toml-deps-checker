"""Rule: catalog.inconsistent-naming — mix of camelCase and kebab-case alias keys."""

from __future__ import annotations

import re

from gradle_deps_monitor.domain.catalog import Catalog
from gradle_deps_monitor.domain.finding import Finding, Severity

ID = "catalog.inconsistent-naming"
SEVERITY = Severity.WARNING

_KEBAB_RE = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")
_CAMEL_RE = re.compile(r"^[a-z][a-zA-Z0-9]*[A-Z][a-zA-Z0-9]*$")


def _style(alias: str) -> str | None:
    """Return 'kebab-case', 'camelCase', or None (unrecognised / single word)."""
    if _KEBAB_RE.match(alias):
        return "kebab-case"
    if _CAMEL_RE.match(alias):
        return "camelCase"
    return None


def check(catalog: Catalog) -> list[Finding]:
    """Return a finding when aliases use both camelCase and kebab-case."""
    all_aliases = (
        [lib.alias for lib in catalog.libraries]
        + [p.alias for p in catalog.plugins]
        + [b.alias for b in catalog.bundles]
    )

    styles: set[str] = set()
    for alias in all_aliases:
        s = _style(alias)
        if s:
            styles.add(s)

    if len(styles) <= 1:
        return []

    return [
        Finding(
            rule_id=ID,
            severity=SEVERITY,
            message="Mixed naming conventions detected (camelCase and kebab-case)",
            details=(
                "Pick one convention for all alias keys. "
                "kebab-case is the Gradle default; camelCase is also acceptable "
                "but mixing both makes the catalog harder to navigate."
            ),
        )
    ]
