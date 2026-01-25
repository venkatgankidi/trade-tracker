"""Configuration settings for the trade tracker application."""

class Config:
    # Cache TTL settings (in seconds)
    CACHE_TTL = {
        'prices': 60,           # Stock prices
        'option_chains': 30,    # Option chains (market hours)
        'portfolio': 300,       # Portfolio calculations
        'dashboard': 300,       # Dashboard data
        'positions': 60,        # Position data
        'platforms': 3600,      # Platform data (static)
        'taxes': 3600,          # Tax data (historical)
    }
    
    # Performance settings
    PAGE_SIZE = 100
    MAX_CONCURRENT_REQUESTS = 5
    DB_CONNECTION_TTL = 3600   # 1 hour
    
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