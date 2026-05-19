-- tools/analytics/schema.sql
--
-- Typed DuckDB schema for the two RFC-0017 CSVs. Column names and
-- order MUST match the writers exactly:
--
--   src/gradle_deps_monitor/infrastructure/writers/inventory_csv_writer.py
--   src/gradle_deps_monitor/infrastructure/writers/findings_csv_writer.py
--
-- The runner reads the header row of each CSV and compares it against
-- the column lists below; on mismatch it fails fast with a pointer to
-- RFC-0017. This is the substitute for the explicit `schema_version`
-- field that RFC-0017 declined to add to the CSVs (see ADR-0010).
--
-- Empty cells in CSV are read as SQL NULL (DuckDB default). Empty
-- means "scanner not run" per RFC-0017; queries that depend on opt-in
-- scanners (`--risk-score`, `--module-usage`, `--cve-scan`) gate with
-- `IS NOT NULL`.

CREATE TABLE inventory (
    alias                VARCHAR,
    coordinate           VARCHAR,
    version              VARCHAR,
    stability_tier       VARCHAR,   -- stable | pre_1_0 | rc | beta | alpha | dev | snapshot | unknown
    latest_stable        VARCHAR,
    drift                VARCHAR,   -- none | patch | minor | major | unknown
    risk_score           INTEGER,   -- 0-100; NULL when --risk-score off
    risk_level           VARCHAR,   -- LOW | MEDIUM | HIGH | CRITICAL | NONE; NULL when --risk-score off
    usage_count          INTEGER,   -- NULL when --module-usage off
    vulnerability_count  INTEGER,   -- NULL when CVE scanner not injected
    compliance_issues    VARCHAR,   -- comma-separated rule IDs
    license_tier         VARCHAR,   -- permissive | weak_copyleft | strong_copyleft | proprietary | unknown
    health_status        VARCHAR,   -- active | deprecated | relocated | inactive
    bom_parent           VARCHAR,   -- alias of managing BoM, empty when none
    duplicate_of         VARCHAR    -- comma-separated other aliases sharing group:artifact
);

CREATE TABLE findings (
    section              VARCHAR,   -- Catalog Health | Compliance | Toolchain | Library Health | Security | License | Changelog
    rule_id              VARCHAR,   -- finding identifier (may have synthetic prefixes: library-health.* license.* changelog.*)
    severity             VARCHAR,   -- section-specific domain value
    common_severity      VARCHAR,   -- ERROR | WARNING | INFO (normalized)
    target               VARCHAR,   -- alias or "catalog"
    message              VARCHAR,
    recommendation       VARCHAR
);
