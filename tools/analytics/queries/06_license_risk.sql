-- 06_license_risk.sql
--
-- Libraries whose license tier is anything except `permissive` —
-- weak_copyleft, strong_copyleft, proprietary, or unknown. The
-- compliance review cohort for the freeze. Permissive libraries are
-- the silent majority and excluded; this is the "stuff a lawyer
-- might want to look at" list.
--
-- Canonical because:
--   1. Generalizable: every Android catalog has at least one
--      non-permissive entry (typically `junit` weak_copyleft, often
--      one or two `unknown`).
--   2. Repeatable: legal / compliance asks every release cycle.
--   3. Compresses signal: typically <10 rows on a 200-library
--      catalog; on Sunflower it's 2.
--   4. Self-contained: single SELECT with WHERE IN. Portable to
--      DuckDB-WASM.
--
-- Sorted by tier severity (strong > weak > proprietary > unknown)
-- so the most concerning rows appear first.

SELECT
    alias,
    coordinate,
    version,
    license_tier
FROM inventory
WHERE license_tier IS NOT NULL
  AND license_tier IN (
    'strong_copyleft',
    'weak_copyleft',
    'proprietary',
    'unknown'
)
ORDER BY
    CASE license_tier
        WHEN 'strong_copyleft' THEN 0
        WHEN 'weak_copyleft'   THEN 1
        WHEN 'proprietary'     THEN 2
        WHEN 'unknown'         THEN 3
        ELSE 4
    END,
    alias;
