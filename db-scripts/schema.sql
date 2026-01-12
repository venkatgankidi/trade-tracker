CREATE TABLE platforms (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) NOT NULL UNIQUE,
    -- Per-platform cash available (true account value). Can be used to store cash, dividends, interest, rewards, etc.
    cash_available NUMERIC(12, 2) DEFAULT 0
);

CREATE TABLE trades (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(10) NOT NULL,
    platform_id INT NOT NULL REFERENCES platforms(id),
    price NUMERIC(10, 2) NOT NULL,
    quantity NUMERIC(10,5) NOT NULL,
    date DATE NOT NULL,
    trade_type VARCHAR(10) NOT NULL
);

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

-- Application metadata table for small key/value settings (e.g. last CSV upload time)
-- Application metadata table for small key/value settings (e.g. last CSV upload time)
CREATE TABLE IF NOT EXISTS app_metadata (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS cash_flows (
    id SERIAL PRIMARY KEY,
    platform_id INTEGER NOT NULL REFERENCES platforms(id),
    flow_type VARCHAR(16) CHECK (flow_type IN ('deposit', 'withdrawal')) NOT NULL,
    amount NUMERIC(12, 2) NOT NULL,
    flow_date DATE NOT NULL,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_cash_flows_platform_date ON cash_flows(platform_id, flow_date);

-- Indexes for trades table (frequently filtered by platform_id, date, ticker)
CREATE INDEX IF NOT EXISTS idx_trades_platform_id ON trades(platform_id);
CREATE INDEX IF NOT EXISTS idx_trades_date ON trades(date);
CREATE INDEX IF NOT EXISTS idx_trades_ticker_platform ON trades(ticker, platform_id);

-- Indexes for positions table (frequently filtered by status, platform_id, ticker)
CREATE INDEX IF NOT EXISTS idx_positions_status ON positions(position_status);
CREATE INDEX IF NOT EXISTS idx_positions_platform_id ON positions(platform_id);
CREATE INDEX IF NOT EXISTS idx_positions_ticker_platform ON positions(ticker, platform_id);

-- Indexes for option_trades table (frequently filtered by status, platform_id)
CREATE INDEX IF NOT EXISTS idx_option_trades_status ON option_trades(status);
CREATE INDEX IF NOT EXISTS idx_option_trades_platform_id ON option_trades(platform_id);
CREATE INDEX IF NOT EXISTS idx_option_trades_status_platform ON option_trades(status, platform_id);

-- Index for app_metadata key lookups
CREATE INDEX IF NOT EXISTS idx_app_metadata_key ON app_metadata(key);

-- Partial indexes for historical reports (trades with specific statuses)
CREATE INDEX IF NOT EXISTS idx_positions_exit_date ON positions(exit_date) WHERE position_status = 'close';
CREATE INDEX IF NOT EXISTS idx_option_trades_close_date ON option_trades(close_date) WHERE status IN ('closed', 'expired');

