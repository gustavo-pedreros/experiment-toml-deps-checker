-- 02_drift_by_severity.sql
--
-- How much of the catalog is `major drift` × `HIGH risk` vs `none` ×
-- `LOW` etc. — the go/no-go bucket counts every reviewer wants in one
-- glance.
--
-- Canonical because:
--   1. Generalizable: every catalog with risk scoring has a drift
--      distribution to summarise.
--   2. Repeatable: asked every freeze ("how outdated am I, severity-
--      weighted?").
--   3. Compresses signal: at most 5 drift × 5 risk_level = 25 rows,
--      independent of catalog size; in practice far fewer.
--   4. Self-contained: single SELECT with GROUP BY. Portable to
--      DuckDB-WASM.
--
-- Gated on `risk_level IS NOT NULL` so the section renders empty when
-- `--risk-score` was off at check time. Rows where drift IS NULL are
-- bucketed as 'unknown' to keep the table simple.

SELECT
    COALESCE(drift, 'unknown') AS drift,
    risk_level,
    COUNT(*) AS libraries
FROM inventory
WHERE risk_level IS NOT NULL
GROUP BY drift, risk_level
ORDER BY
    CASE risk_level
        WHEN 'CRITICAL' THEN 0
        WHEN 'HIGH' THEN 1
        WHEN 'MEDIUM' THEN 2
        WHEN 'LOW' THEN 3
        WHEN 'NONE' THEN 4
        ELSE 5
    END,
    CASE drift
        WHEN 'major' THEN 0
        WHEN 'minor' THEN 1
        WHEN 'patch' THEN 2
        WHEN 'none' THEN 3
        ELSE 4
    END;
