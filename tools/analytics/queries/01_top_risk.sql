-- 01_top_risk.sql
--
-- Top 15 libraries by composite risk score, with the dimensions that
-- explain the score joined into the same row. The first thing a
-- reviewer should look at after a `--risk-score` run.
--
-- Canonical because:
--   1. Generalizable: every Android catalog with risk scoring asks
--      "what should I triage first?"
--   2. Repeatable: every freeze. Risk is the headline number.
--   3. Compresses signal: 15 rows × 7 cols regardless of catalog size.
--   4. Self-contained: single SELECT against `inventory`. No CTEs,
--      no DuckDB-only extensions. Portable to DuckDB-WASM.
--
-- Gated on `risk_score IS NOT NULL` so the section renders cleanly
-- when `--risk-score` was off at check time (empty result → "no rows"
-- footer in render.py).

SELECT
    alias,
    coordinate,
    version,
    risk_score,
    risk_level,
    drift,
    COALESCE(vulnerability_count, 0) AS cves,
    license_tier
FROM inventory
WHERE risk_score IS NOT NULL
ORDER BY risk_score DESC, alias ASC
LIMIT 15;
