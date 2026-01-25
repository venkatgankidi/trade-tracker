-- Consolidated schema with optimized indexes for trade tracker
-- This file contains both table definitions and performance-optimized indexes

-- PLATFORMS TABLE
CREATE TABLE platforms (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) NOT NULL UNIQUE,
    -- Per-platform cash available (true account value). Can be used to store cash, dividends, interest, rewards, etc.
    cash_available NUMERIC(12, 2) DEFAULT 0
);

-- TRADES TABLE
CREATE TABLE trades (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(10) NOT NULL,
    platform_id INT NOT NULL REFERENCES platforms(id),
    price NUMERIC(10, 2) NOT NULL,
    quantity NUMERIC(10,5) NOT NULL,
    date DATE NOT NULL,
    trade_type VARCHAR(10) NOT NULL
);

-- POSITIONS TABLE
CREATE TABLE IF NOT EXISTS positions (
    id SERIAL PRIMARY KEY,
    ticker TEXT NOT NULL,
    trade_type TEXT,
    position_status TEXT NOT NULL, -- 'open' or 'close'
    entry_price REAL,
    quantity REAL,
    exit_price REAL,
    exit_date DATE DEFAULT NULL,
    entry_date DATE DEFAULT CURRENT_DATE,
    profit_loss REAL,
    platform_id INTEGER REFERENCES platforms(id)
);

-- OPTION TRADES TABLE
CREATE TABLE IF NOT EXISTS option_trades (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(16) NOT NULL,
    platform_id INTEGER REFERENCES platforms(id),
    strategy VARCHAR(32) NOT NULL,
    strike_price NUMERIC(12, 4) NOT NULL,
    expiry_date DATE NOT NULL,
    trade_date DATE NOT NULL,
    transaction_type VARCHAR(8) CHECK (transaction_type IN ('credit', 'debit')) NOT NULL,
    option_open_price NUMERIC(12, 4) NOT NULL,
    open_fee NUMERIC(10, 4) DEFAULT 0,
    option_close_price NUMERIC(12, 4),
    close_fee NUMERIC(10, 4) DEFAULT 0,
    profit_loss NUMERIC(12, 4),
    status VARCHAR(16) CHECK (status IN ('open', 'expired', 'exercised','closed')) DEFAULT 'open',
    close_date DATE,
    notes TEXT
);

-- APPLICATION METADATA TABLE
-- For small key/value settings (e.g. last CSV upload time)
CREATE TABLE IF NOT EXISTS app_metadata (
    key TEXT PRIMARY KEY,
    value TEXT
);

-- CASH FLOWS TABLE
CREATE TABLE IF NOT EXISTS cash_flows (
    id SERIAL PRIMARY KEY,
    platform_id INTEGER NOT NULL REFERENCES platforms(id),
    flow_type VARCHAR(16) CHECK (flow_type IN ('deposit', 'withdrawal')) NOT NULL,
    amount NUMERIC(12, 2) NOT NULL,
    flow_date DATE NOT NULL,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- OPTIMIZED INDEXES
-- ============================================================================

-- TRADES TABLE INDEXES
-- Primary composite index for sync_positions_from_trades optimization
CREATE INDEX IF NOT EXISTS idx_trades_ticker_platform_date_id ON trades(ticker, platform_id, date, id);

-- Supporting indexes for various query patterns
CREATE INDEX IF NOT EXISTS idx_trades_date ON trades(date);
CREATE INDEX IF NOT EXISTS idx_trades_platform_id ON trades(platform_id);

-- Note: idx_trades_ticker_platform from original schema is redundant with 
-- idx_trades_ticker_platform_date_id for most queries, so removed to avoid duplication

-- POSITIONS TABLE INDEXES
-- Most frequently queried columns
CREATE INDEX IF NOT EXISTS idx_positions_status ON positions(position_status);
CREATE INDEX IF NOT EXISTS idx_positions_platform_id ON positions(platform_id);

-- Composite indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_positions_ticker_platform ON positions(ticker, platform_id);
CREATE INDEX IF NOT EXISTS idx_positions_platform_status ON positions(platform_id, position_status);
CREATE INDEX IF NOT EXISTS idx_positions_entry_date ON positions(entry_date);

-- Partial index for historical reports (only closed positions)
CREATE INDEX IF NOT EXISTS idx_positions_exit_date ON positions(exit_date) WHERE position_status = 'close';

-- OPTION TRADES TABLE INDEXES
-- Single column indexes for basic filtering
CREATE INDEX IF NOT EXISTS idx_option_trades_status ON option_trades(status);
CREATE INDEX IF NOT EXISTS idx_option_trades_platform_id ON option_trades(platform_id);
CREATE INDEX IF NOT EXISTS idx_option_trades_expiry ON option_trades(expiry_date);
CREATE INDEX IF NOT EXISTS idx_option_trades_trade_date ON option_trades(trade_date);

-- Composite indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_option_trades_ticker_status ON option_trades(ticker, status);
CREATE INDEX IF NOT EXISTS idx_option_trades_platform_status ON option_trades(platform_id, status);

-- Partial index for historical reports (only closed/expired trades)
CREATE INDEX IF NOT EXISTS idx_option_trades_close_date ON option_trades(close_date) WHERE status IN ('closed', 'expired');

-- CASH FLOWS TABLE INDEXES
-- Primary composite index for platform-specific cash flow queries
CREATE INDEX IF NOT EXISTS idx_cash_flows_platform_date ON cash_flows(platform_id, flow_date);

-- Supporting index for date-based queries
CREATE INDEX IF NOT EXISTS idx_cash_flows_date ON cash_flows(flow_date);

-- LOOKUP TABLE INDEXES
-- Index for platforms name lookups
CREATE INDEX IF NOT EXISTS idx_platforms_name ON platforms(name);

-- Index for app_metadata key lookups
CREATE INDEX IF NOT EXISTS idx_app_metadata_key ON app_metadata(key);
