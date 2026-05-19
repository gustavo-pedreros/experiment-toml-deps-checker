-- 08_bom_coverage.sql
--
-- BoM (Bill of Materials) cohort sizes per RFC-0014: how many catalog
-- libraries are managed by each BoM. Tells the reviewer whether BoM
-- adoption is consistent (most compose libs under
-- `androidx-compose-bom`) or fragmented (some compose libs free-
-- floating, breaking the BoM's version-pinning contract).
--
-- Canonical because:
--   1. Generalizable: BoMs are an upstream Maven feature, used by
--      most modern Android catalogs (Compose BoM, Firebase BoM,
--      OkHttp/Retrofit BoM…).
--   2. Repeatable: every freeze should validate BoM hygiene.
--   3. Compresses signal: one row per BoM cohort — at most ~5 BoMs
--      in a typical catalog.
--   4. Self-contained: single SELECT with GROUP BY. Portable to
--      DuckDB-WASM.
--
-- The "not under a BoM" cohort (bom_parent = '') is the largest by
-- definition (libraries pinned directly via version refs); it's
-- included to make the relative share visible. The reviewer should
-- ask: are any of these libraries siblings of a known BoM cohort
-- that should be brought in?

SELECT
    CASE
        WHEN bom_parent IS NULL OR bom_parent = '' THEN '(unmanaged)'
        ELSE bom_parent
    END AS bom_parent,
    COUNT(*) AS libraries_in_cohort
FROM inventory
GROUP BY 1
ORDER BY libraries_in_cohort DESC, bom_parent;
