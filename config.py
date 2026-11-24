"""Configuration settings for the trade tracker application."""

class Config:
    # Cache TTL settings (in seconds)
    CACHE_TTL = {
        'prices': 60,           # Stock prices
        'option_chains': 30,    # Option chains (market hours)
        'portfolio': 300,       # Portfolio calculations
        'dashboard': 300,       # Dashboard data
        'positions': 300,       # Position data (invalidated on write)
        'option_trades': 300,   # Option trades & legs (invalidated on write)
        'trades': 600,          # Raw trade history (invalidated on write)
        'cash_flows': 300,      # Cash flows & platform cash (invalidated on write)
        'platforms': 3600,      # Platform data (static)
        'metadata': 300,        # App metadata such as last upload timestamp
        'taxes': 3600,          # Tax data (historical)
        'reports': 300,         # Weekly/monthly P/L reports
    }
    
    # Performance & DB memory settings
    PAGE_SIZE = 100
    MAX_CONCURRENT_REQUESTS = 5
    DB_CONNECTION_TTL = 3600   # 1 hour (legacy constant)
    DB_BATCH_SIZE = 200        # Max rows per executemany chunk to cap DB parse/bind memory
    # Direct-connection session guardrails for low-RAM PostgreSQL (e.g. Aiven Free Tier without PgBouncer)
    DB_CONNECT_ARGS = {
        "options": (
            "-c work_mem=2MB "
            "-c statement_timeout=30000 "
            "-c idle_in_transaction_session_timeout=15000"
        )
    }
    
    # UI settings
    DEFAULT_CHART_HEIGHT = 400
    MAX_PIE_CHARTS_PER_ROW = 3
    
    # Market data settings
    MARKET_HOURS_START = 9.5   # 9:30 AM
    MARKET_HOURS_END = 16.0    # 4:00 PM
    MARKET_TIMEZONE = 'America/New_York'
    
    # Option settings
    OPTION_CONTRACT_SIZE = 100
    DEFAULT_OPTION_TTL = 30     # seconds during market hours
    
    # Data validation
    MAX_QUANTITY_DECIMALS = 6
    MAX_PRICE_DECIMALS = 4
    MAX_PROFIT_LOSS_DECIMALS = 2