-- 04_unstable_prerelease_in_prod.sql
--
-- Libraries pinned at a pre-release stability tier in the catalog
-- (alpha / beta / rc / pre_1_0 / snapshot / dev / unknown). These ship
-- with weaker stability guarantees than a `stable` release and merit
-- a deliberate review at freeze time — even if no other dimension
-- flags them.
--
-- Canonical because:
--   1. Generalizable: pre-release tiers are universal across the
--      Maven ecosystem (RFC-0026 + RFC-0027 surfaced them as first-
--      class enums).
--   2. Repeatable: reviewers ask "what's still pre-release in my
--      catalog?" every freeze.
--   3. Compresses signal: pre-release libs are a minority of the
--      catalog; on Sunflower it's 5 of 50.
--   4. Self-contained: single SELECT with WHERE IN. Portable to
--      DuckDB-WASM.
--
-- Tier ordering reflects perceived risk (alpha > beta > rc > pre_1_0
-- > snapshot > dev > unknown). Stable is excluded by definition.

SELECT
    alias,
    coordinate,
    version,
    stability_tier,
    drift,
    latest_stable
FROM inventory
WHERE stability_tier IN (
    'alpha', 'beta', 'rc', 'pre_1_0', 'snapshot', 'dev', 'unknown'
)
ORDER BY
    CASE stability_tier
        WHEN 'alpha'    THEN 0
        WHEN 'beta'     THEN 1
        WHEN 'rc'       THEN 2
        WHEN 'pre_1_0'  THEN 3
        WHEN 'snapshot' THEN 4
        WHEN 'dev'      THEN 5
        WHEN 'unknown'  THEN 6
        ELSE 7
    END,
    alias;
