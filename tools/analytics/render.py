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
TITLES: dict[str, str] = {
    "top_risk": "Top risk",
}


def section_title(query_name: str) -> str:
    """Return the display title for a query name; fall back to the name itself."""
    return TITLES.get(query_name, query_name.replace("_", " ").title())


def render_section(query_name: str, rel: duckdb.DuckDBPyRelation) -> str:
    """Render a query result as a Markdown section.

    Reads ``rel.columns`` for headers and ``rel.fetchall()`` for the
    body rows, then formats as a GitHub-flavoured Markdown table via
    ``tabulate``. No pandas anywhere by design (ADR-0010).
    """
    title = section_title(query_name)
    columns = rel.columns
    rows = rel.fetchall()
    if not rows:
        return f"## {title}\n\n> No rows for this query against this report.\n"
    table = tabulate(rows, headers=columns, tablefmt="github")
    return f"## {title}\n\n{table}\n"


def render_document(sections: list[str], report_dir: str) -> str:
    """Combine rendered sections into a single Markdown document."""
    header = f"# Freeze report analysis — `{report_dir}`\n\n"
    return header + "\n".join(sections)
