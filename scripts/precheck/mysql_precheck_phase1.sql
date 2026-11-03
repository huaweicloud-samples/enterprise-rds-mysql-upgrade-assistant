-- MySQL 8.0 -> 8.4 pre-upgrade compatibility checks (engine-agnostic).
-- Run against the source instance before a major version upgrade.
-- Executed by rds_upgrade_mcp.huaweicloud_backend.run_precheck_sql via `mysql ... source <file>`.

-- 1. Authentication plugin in use (8.4 requires caching_sha2_password / mysql_native_password)
SELECT 'default_authentication_plugin' AS check_name, @@default_authentication_plugin AS current_value;

-- 2. Schemas / columns not using utf8mb4 (8.4 tightens charset handling)
SELECT table_schema, table_name, column_name, character_set_name
FROM information_schema.columns
WHERE character_set_name IS NOT NULL
  AND character_set_name NOT IN ('utf8mb4', 'binary')
LIMIT 50;

-- 3. Current sql_mode (ensure no removed modes)
SELECT @@sql_mode AS current_sql_mode;

-- 4. Identifiers that collide with reserved words introduced in newer MySQL
SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_name IN ('RANK', 'ROW', 'NULLS', 'GROUPING', 'LATERAL', 'EXCEPT', 'INTERSECT')
LIMIT 50;

-- 5. Views that may reference removed system variables / features
SELECT table_schema, table_name
FROM information_schema.views
LIMIT 200;

-- 6. Tables using deprecated explicit ROW_FORMAT / storage engine hints
SELECT table_schema, table_name, engine, row_format
FROM information_schema.tables
WHERE engine IS NOT NULL AND engine NOT IN ('InnoDB')
LIMIT 100;
