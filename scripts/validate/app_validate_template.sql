-- Post-upgrade application validation checks (engine-agnostic).
-- Run against the upgraded (green) instance to confirm functional readiness.
-- Executed by rds_upgrade_mcp tools.app_validate via run_precheck_sql.

-- 1. Confirm the engine version actually moved to the target family
SELECT VERSION() AS current_version;

-- 2. Confirm all expected schemas are present and accessible
SELECT schema_name FROM information_schema.schemata
WHERE schema_name NOT IN ('information_schema', 'mysql', 'performance_schema', 'sys')
ORDER BY schema_name;

-- 3. Confirm tables are reachable (sample probe of user schemas)
SELECT table_schema, table_name, table_rows
FROM information_schema.tables
WHERE table_schema NOT IN ('information_schema', 'mysql', 'performance_schema', 'sys')
ORDER BY table_schema, table_name
LIMIT 200;

-- 4. Confirm character set is utf8mb4 end-to-end
SELECT DEFAULT_CHARACTER_SET_NAME, DEFAULT_COLLATION_NAME
FROM information_schema.schemata
WHERE schema_name NOT IN ('information_schema', 'mysql', 'performance_schema', 'sys');
