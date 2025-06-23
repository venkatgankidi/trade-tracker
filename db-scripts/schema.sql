CREATE TABLE platforms (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) NOT NULL UNIQUE
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

