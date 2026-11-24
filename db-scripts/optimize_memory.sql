-- ============================================================================
-- Aiven Free Tier PostgreSQL Memory Optimization & Maintenance Script
-- ============================================================================
-- Safe and idempotent. Run this once against your existing Aiven PostgreSQL
-- database (via psql, DBeaver, pgAdmin, or Aiven's SQL editor) to:
--   1. Drop duplicate & unused indexes that occupy shared_buffers RAM and add
--      write/autovacuum overhead during position syncs.
--   2. Reclaim dead tuples left by prior full-table position syncs.
-- ============================================================================

-- 1. Drop 100% duplicate indexes (already covered by PRIMARY KEY / UNIQUE)
DROP INDEX IF EXISTS idx_platforms_name;
DROP INDEX IF EXISTS idx_app_metadata_key;

-- 2. Drop redundant / unused indexes not queried by the application
DROP INDEX IF EXISTS idx_trades_platform_id;
DROP INDEX IF EXISTS idx_positions_status;
DROP INDEX IF EXISTS idx_positions_platform_id;
DROP INDEX IF EXISTS idx_positions_platform_status;
DROP INDEX IF EXISTS idx_positions_exit_date;
DROP INDEX IF EXISTS idx_option_trades_platform_id;
DROP INDEX IF EXISTS idx_option_trades_expiry;
DROP INDEX IF EXISTS idx_option_trades_trade_date;
DROP INDEX IF EXISTS idx_option_trades_ticker_status;
DROP INDEX IF EXISTS idx_option_trades_platform_status;
DROP INDEX IF EXISTS idx_option_trades_close_date;
DROP INDEX IF EXISTS idx_cash_flows_platform_date;

-- 3. Ensure minimal supporting index for cash_flows platform join exists
CREATE INDEX IF NOT EXISTS idx_cash_flows_platform_id ON cash_flows(platform_id);

-- 4. Reclaim dead tuples and refresh planner statistics
-- Note: VACUUM cannot run inside a multi-statement transaction block.
-- Run each VACUUM ANALYZE statement individually if your SQL client wraps scripts in BEGIN/COMMIT.
VACUUM ANALYZE platforms;
VACUUM ANALYZE trades;
VACUUM ANALYZE positions;
VACUUM ANALYZE option_trades;
VACUUM ANALYZE option_trade_legs;
VACUUM ANALYZE cash_flows;
VACUUM ANALYZE app_metadata;

-- ============================================================================
-- Optional Diagnostics (run separately to inspect Aiven PostgreSQL health)
-- ============================================================================
-- Check active/idle connections:
--   SELECT state, count(*) FROM pg_stat_activity WHERE datname = current_database() GROUP BY state;
--
-- Check table & index sizes plus dead tuple counts:
--   SELECT relname,
--          n_live_tup,
--          n_dead_tup,
--          pg_size_pretty(pg_table_size(relid)) AS table_size,
--          pg_size_pretty(pg_indexes_size(relid)) AS index_size
--   FROM pg_stat_user_tables
--   ORDER BY pg_total_relation_size(relid) DESC;
