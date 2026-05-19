"""Markdown rendering for analytics query results.

Per ADR-0010, this module is the only allowed presentation-layer
touchpoint. Compute happens in SQL (``queries/*.sql``); this file
only formats a DuckDB relation as a Markdown table via ``tabulate``.

If you find yourself needing column transforms, groupings, or any
other "tidy-up" of the rows here — stop and move it to SQL. The
``.sql`` files are the asset that survives the future port to
DuckDB-WASM (RFC-0010 HTML export); this Python is throwaway in
that scenario.
"""

from __future__ import annotations

import duckdb
from tabulate import tabulate

# Human-readable titles per query name. Keep in sync with the
# queries/*.sql filenames (strip leading "NN_" and look up here).
# Section titles use the multiplication sign (U+00D7) intentionally
# as the cross-product operator -- matches how the same concept reads
# in freeze.md tables and in the User Guide. ruff RUF001 (ambiguous
# unicode in strings) is suppressed per occurrence.
TITLES: dict[str, str] = {
    "top_risk": "Top risk",
    "drift_by_severity": "Drift × severity",  # noqa: RUF001
    "compound_security_duplicates": "Compound: duplicates with CVEs",
    "unstable_prerelease_in_prod": "Pre-release tiers in the catalog",
    "inactive_or_unhealthy": "Inactive / unhealthy libraries",
    "license_risk": "License risk cohort",
    "finding_severity_breakdown": "Findings by section × severity",  # noqa: RUF001
    "bom_coverage": "BoM coverage",
}

# Query name → full sentence shown when the query returns no rows
# because the upstream scanner didn't run for this freeze.
_SCANNER_HINTS: dict[str, str] = {
    "top_risk": ("Re-run `gradle-deps-monitor check --risk-score` to populate this section."),
    "drift_by_severity": (
        "Re-run `gradle-deps-monitor check --risk-score` to populate this section."
    ),
    "compound_security_duplicates": (
        "Re-run `gradle-deps-monitor check` with `GITHUB_TOKEN` set "
        "(CVE scanner — see Credentials in README.md) to populate this section."
    ),
}


def section_title(query_name: str) -> str:
    """Return the display title for a query name; fall back to the name itself."""
    return TITLES.get(query_name, query_name.replace("_", " ").title())


def _empty_section(query_name: str, title: str, scanner_columns_all_null: bool) -> str:
    """Render the empty-result block, with a scanner-not-run hint when applicable."""
    if scanner_columns_all_null and query_name in _SCANNER_HINTS:
        hint = _SCANNER_HINTS[query_name]
        return f"## {title}\n\n> Scanner not run for this dimension. {hint}\n"
    return f"## {title}\n\n> No rows for this query against this report.\n"


def render_section(
    query_name: str,
    rel: duckdb.DuckDBPyRelation,
    *,
    scanner_columns_all_null: bool = False,
) -> str:
    """Render a query result as a Markdown section.

    Reads ``rel.columns`` for headers and ``rel.fetchall()`` for the
    body rows, then formats as a GitHub-flavoured Markdown table via
    ``tabulate``. No pandas anywhere by design (ADR-0010).

    ``scanner_columns_all_null`` is set by the runner when the
    opt-in column the query depends on (e.g. ``risk_score`` for
    ``top_risk``) is uniformly NULL across the inventory — meaning
    the user ran ``gradle-deps-monitor check`` without the relevant
    flag. The empty-section renderer turns that signal into an
    actionable hint instead of a generic "no rows" footer.
    """
    title = section_title(query_name)
    columns = rel.columns
    rows = rel.fetchall()
    if not rows:
        return _empty_section(query_name, title, scanner_columns_all_null)
    table = tabulate(rows, headers=columns, tablefmt="github")
    return f"## {title}\n\n{table}\n"


def render_document(sections: list[str], report_dir: str) -> str:
    """Combine rendered sections into a single Markdown document."""
    header = f"# Freeze report analysis — `{report_dir}`\n\n"
    return header + "\n".join(sections)
