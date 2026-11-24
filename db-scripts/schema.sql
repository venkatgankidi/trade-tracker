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
    trade_type VARCHAR(10) NOT NULL,
    direction VARCHAR(5) NOT NULL DEFAULT 'Long'  -- 'Long' or 'Short'
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
    platform_id INTEGER REFERENCES platforms(id),
    direction VARCHAR(5) DEFAULT 'Long'  -- 'Long' or 'Short'
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
    notes TEXT,
    quantity INTEGER DEFAULT 1
);

-- OPTION TRADE LEGS TABLE (for multi-leg strategies: spreads, condors, etc.)
CREATE TABLE IF NOT EXISTS option_trade_legs (
    id SERIAL PRIMARY KEY,
    option_trade_id INTEGER NOT NULL REFERENCES option_trades(id) ON DELETE CASCADE,
    leg_type VARCHAR(4) NOT NULL CHECK (leg_type IN ('call', 'put')),
    side VARCHAR(4) NOT NULL CHECK (side IN ('buy', 'sell')),
    strike_price NUMERIC(12, 4) NOT NULL,
    expiry_date DATE NOT NULL,
    premium NUMERIC(12, 4) NOT NULL DEFAULT 0,
    close_premium NUMERIC(12, 4)
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
-- OPTIMIZED INDEXES (minimal set to reduce shared_buffers & vacuum memory
-- overhead on low-memory PostgreSQL tiers such as Aiven Free Plan)
-- ============================================================================

-- TRADES TABLE INDEXES
-- Primary composite index for sync_positions_from_trades ORDER BY (ticker, platform_id, date, id)
CREATE INDEX IF NOT EXISTS idx_trades_ticker_platform_date_id ON trades(ticker, platform_id, date, id);
-- Supports load_all_trades ORDER BY (date, id)
CREATE INDEX IF NOT EXISTS idx_trades_date ON trades(date, id);

-- POSITIONS TABLE INDEXES
-- Supports sync_positions_from_trades DELETE WHERE ticker = ... AND platform_id = ...
CREATE INDEX IF NOT EXISTS idx_positions_ticker_platform ON positions(ticker, platform_id);
-- Supports load_all_positions ORDER BY entry_date DESC
CREATE INDEX IF NOT EXISTS idx_positions_entry_date ON positions(entry_date DESC);

-- OPTION TRADES TABLE INDEXES
-- Supports optional status filtering
CREATE INDEX IF NOT EXISTS idx_option_trades_status ON option_trades(status);

-- OPTION TRADE LEGS TABLE INDEXES
-- Supports FK lookups and ORDER BY option_trade_id, id
CREATE INDEX IF NOT EXISTS idx_option_trade_legs_trade_id ON option_trade_legs(option_trade_id, id);

-- CASH FLOWS TABLE INDEXES
-- Supports load_cash_flows ORDER BY flow_date DESC and platform JOIN
CREATE INDEX IF NOT EXISTS idx_cash_flows_date ON cash_flows(flow_date DESC);
CREATE INDEX IF NOT EXISTS idx_cash_flows_platform_id ON cash_flows(platform_id);

-- Note: platforms(name) already has a UNIQUE index and app_metadata(key) already
-- has a PRIMARY KEY index; duplicate indexes are intentionally omitted.
