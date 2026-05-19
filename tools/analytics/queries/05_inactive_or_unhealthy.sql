-- 05_inactive_or_unhealthy.sql
--
-- Libraries whose RFC-0006 library-health signal is anything other
-- than `active` — inactive, deprecated, relocated. These need a
-- replacement plan; carrying them quietly in the catalog accumulates
-- maintenance debt.
--
-- Canonical because:
--   1. Generalizable: the library-health KB + POM <relocation> +
--      inactivity heuristic produces a `health_status` for every
--      catalog.
--   2. Repeatable: every freeze should answer "what should we
--      migrate off?"
--   3. Compresses signal: actively maintained libs are the majority;
--      this query surfaces the minority that need attention.
--   4. Self-contained: single SELECT with WHERE filter. Portable to
--      DuckDB-WASM.
--
-- Gated on `health_status IS NOT NULL` to handle catalogs where the
-- library-health checker didn't run for some libraries (e.g. POM not
-- reachable). `usage_count` is shown when --module-usage is on so the
-- reviewer can prioritise replacements by blast radius.

SELECT
    alias,
    coordinate,
    version,
    health_status,
    COALESCE(usage_count, 0) AS modules_using
FROM inventory
WHERE health_status IS NOT NULL
  AND health_status <> 'active'
ORDER BY
    CASE health_status
        WHEN 'deprecated' THEN 0
        WHEN 'relocated'  THEN 1
        WHEN 'inactive'   THEN 2
        ELSE 3
    END,
    modules_using DESC,
    alias;
