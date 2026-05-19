-- 07_finding_severity_breakdown.sql
--
-- Distribution of findings by section × normalized severity. "Where
-- are my ERRORs?" — one-shot bucket counts across all RFC-0017
-- sections (Catalog Health, Compliance, Toolchain, Library Health,
-- Security, License, Changelog).
--
-- Canonical because:
--   1. Generalizable: every freeze produces findings; this
--      cross-section view is the natural triage entry point.
--   2. Repeatable: the same first question every release cycle.
--   3. Compresses signal: at most ~7 sections × ~4 severities =
--      ~28 rows, independent of catalog size.
--   4. Self-contained: single SELECT with GROUP BY. Portable to
--      DuckDB-WASM.
--
-- Severity ordering follows the CommonSeverity enum (error > warning
-- > info > suggestion). Sections appear in the order they're written
-- to freeze.md for visual consistency.

SELECT
    section,
    common_severity,
    COUNT(*) AS findings
FROM findings
GROUP BY section, common_severity
ORDER BY
    CASE section
        WHEN 'Security'         THEN 0
        WHEN 'Compliance'       THEN 1
        WHEN 'Toolchain'        THEN 2
        WHEN 'Library Health'   THEN 3
        WHEN 'License'          THEN 4
        WHEN 'Catalog Health'   THEN 5
        WHEN 'Changelog'        THEN 6
        ELSE 7
    END,
    CASE common_severity
        WHEN 'error'      THEN 0
        WHEN 'warning'    THEN 1
        WHEN 'info'       THEN 2
        WHEN 'suggestion' THEN 3
        ELSE 4
    END;
