"""Markdown rendering for analytics query results.

This module is the single allowed pandas touchpoint per ADR-0010.
Compute happens in SQL (queries/*.sql); this file only converts a
DuckDB relation into a Markdown table via pandas.DataFrame.to_markdown().

If you find yourself adding a `df.groupby(...)`, `df.merge(...)`,
`df.apply(...)`, or any other compute call here, stop and move it to
SQL. That's the discipline that keeps queries/*.sql portable to
DuckDB-WASM for the future RFC-0010 HTML export.
"""

from __future__ import annotations

import duckdb

# Human-readable titles per query name. Keep in sync with the
# queries/*.sql filenames (strip leading "NN_" and use this map for
# the display title).
TITLES: dict[str, str] = {
    "top_risk": "Top risk",
}


def section_title(query_name: str) -> str:
    """Return the display title for a query name; fall back to the name itself."""
    return TITLES.get(query_name, query_name.replace("_", " ").title())


def render_section(query_name: str, rel: duckdb.DuckDBPyRelation) -> str:
    """Render a query result as a Markdown section.

    The ONLY allowed pandas touchpoint: ``rel.df()`` followed by
    ``df.to_markdown(index=False)``. Any other ``df.<method>(...)`` call
    here is a violation of ADR-0010.
    """
    title = section_title(query_name)
    df = rel.df()
    if df.empty:
        return f"## {title}\n\n> No rows for this query against this report.\n"
    table = df.to_markdown(index=False)
    return f"## {title}\n\n{table}\n"


def render_document(sections: list[str], report_dir: str) -> str:
    """Combine rendered sections into a single Markdown document."""
    header = f"# Freeze report analysis — `{report_dir}`\n\n"
    return header + "\n".join(sections)
