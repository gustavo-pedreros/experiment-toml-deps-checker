-- 03_compound_security_duplicates.sql
--
-- The RFC-0017 issue-#13 story: duplicate aliases on the same
-- group:artifact where at least one of the duplicates carries a CVE.
-- Catalog Health flags the duplicate; Security separately flags the
-- CVE; the compound — "the duplicate is the reason you're exposed to
-- the older CVE" — is invisible in the narrative `freeze.md`. This
-- query is the canonical exposure surface.
--
-- Canonical because:
--   1. Generalizable: every catalog can accumulate stale duplicate
--      aliases (especially during migrations or vendor swaps).
--   2. Repeatable: a clean catalog returns zero rows; a regressing
--      catalog returns a non-empty result — both are valuable signals
--      every freeze.
--   3. Compresses signal: typically 0-5 rows even on dirty catalogs,
--      vs. the full inventory.
--   4. Self-contained: single SELECT with a self-join on `coordinate`.
--      Portable to DuckDB-WASM.
--
-- Empty result on Sunflower is the expected case (a clean sample
-- catalog). Empty result + clean CVE scan is the "all good" outcome;
-- empty result + scanner-not-run is a different story (handled in
-- render.py via the all-NULL detection for `vulnerability_count`).

SELECT
    a.alias               AS alias,
    a.coordinate          AS coordinate,
    a.version             AS version,
    a.vulnerability_count AS cves_on_this_copy,
    b.alias               AS duplicate_alias,
    b.version             AS duplicate_version,
    b.vulnerability_count AS cves_on_duplicate
FROM inventory a
JOIN inventory b
  ON a.coordinate = b.coordinate
 AND a.alias <> b.alias
WHERE COALESCE(a.vulnerability_count, 0) > 0
   OR COALESCE(b.vulnerability_count, 0) > 0
ORDER BY a.coordinate, a.alias;
