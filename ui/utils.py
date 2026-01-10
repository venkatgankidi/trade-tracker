"""Shared utility functions for the trade tracker UI."""
import pandas as pd
from typing import Dict, List, Optional, Tuple
import yfinance as yf
import streamlit as st
from db.db_utils import PLATFORM_CACHE
import datetime
import pytz


def color_profit_loss(val):
    """Color code profit/loss values: green for positive, red for negative."""
    try:
        v = float(str(val).replace('%', ''))
    except:
        return ""
    color = "green" if v > 0 else ("red" if v < 0 else "black")
    return f"color: {color}"


def get_platform_id_to_name_map() -> Dict[int, str]:
    """Get a mapping of platform IDs to their names."""
    return {v: k for k, v in PLATFORM_CACHE.cache.items()}


def apply_profit_loss_styling(df: pd.DataFrame, cols: List[str]):
    """Apply profit/loss styling to specified columns in a DataFrame.
    
    Args:
        df: The DataFrame to style
        cols: List of column names to apply styling to
        
    Returns:
        Styled DataFrame if columns exist, otherwise returns the DataFrame as-is
    """
    if cols:
        return df.style.map(color_profit_loss, subset=cols)
    return df


def _is_market_open() -> bool:
    """Check if US stock market is currently open (9:30 AM - 4:00 PM ET, Monday-Friday)."""
    try:
        eastern = pytz.timezone('US/Eastern')
        now = datetime.datetime.now(eastern)
        
        # Market is closed on weekends
        if now.weekday() >= 5:
            return False
        
        # Market hours: 9:30 AM - 4:00 PM ET
        market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
        market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)
        
        return market_open <= now <= market_close
    except Exception:
        return False


def _extract_price_from_chain(chain_df, strike: float) -> Optional[float]:
    """Extract option price from chain dataframe using various fallback methods.
    
    Priority: bid-ask midpoint > lastPrice > bid > ask
    """
    matching = chain_df[chain_df['strike'] == strike]
    if matching.empty:
        return None
    
    row = matching.iloc[0]
    
    # Try bid-ask midpoint first
    bid = row.get('bid', 0)
    ask = row.get('ask', 0)
    
    if bid > 0 and ask > 0:
        return (bid + ask) / 2
    elif bid > 0:
        return bid
    elif ask > 0:
        return ask
    
    # Fallback to lastPrice
    last_price = row.get('lastPrice', None)
    if last_price and last_price > 0:
        return last_price
    
    # Fallback to close
    close = row.get('close', None)
    if close and close > 0:
        return close
    
    return None


@st.cache_data(ttl=300, show_spinner=False)
def get_option_chain_for_ticker(ticker: str) -> Optional[Dict]:
    """Fetch option chain data from Yahoo Finance for a given ticker.
    
    Args:
        ticker: Stock ticker symbol (e.g., 'AAPL')
        
    Returns:
        Dictionary with expiration dates and option data, or None if error occurs
    """
    try:
        ticker_obj = yf.Ticker(ticker)
        options = ticker_obj.options  # List of expiration dates
        if not options:
            return None
        return {"ticker": ticker, "expirations": options}
    except Exception as e:
        print(f"Error fetching option chain for {ticker}: {e}")
        return None


@st.cache_data(ttl=300, show_spinner=False)
def get_option_price(ticker: str, expiry: str, strike: float, option_type: str) -> Optional[float]:
    """Fetch current option price from Yahoo Finance.
    
    During market hours: attempts live data
    Outside market hours: uses end-of-day data
    Always falls back to available data if primary source fails
    
    Args:
        ticker: Stock ticker symbol (e.g., 'AAPL')
        expiry: Expiration date as string (e.g., '2025-01-17')
        strike: Strike price
        option_type: 'call' or 'put'
        
    Returns:
        Current option price (bid-ask midpoint) or None if not found
    """
    try:
        ticker_obj = yf.Ticker(ticker)
        opt_chain = ticker_obj.option_chain(expiry)
        
        # Select appropriate chain (calls or puts)
        chain_df = opt_chain.calls if option_type.lower() == 'call' else opt_chain.puts
        
        # Extract price using fallback hierarchy
        price = _extract_price_from_chain(chain_df, strike)
        return price
        
    except Exception as e:
        print(f"Error fetching option price for {ticker} {expiry} {strike} {option_type}: {e}")
        return None


def get_batch_option_prices(ticker: str, options_list: List[Dict]) -> pd.DataFrame:
    """Fetch current prices for multiple options of the same ticker.
    
    Efficiently batches requests by expiration date.
    Uses bid-ask midpoint when available, falls back to lastPrice/close data.
    
    Args:
        ticker: Stock ticker symbol
        options_list: List of option dicts with 'strike', 'expiry', and 'type' keys
        
    Returns:
        DataFrame with current prices added
    """
    try:
        ticker_obj = yf.Ticker(ticker)
        unique_expiries = set(opt.get('expiry') for opt in options_list if opt.get('expiry'))
        
        expiry_data = {}
        for expiry in unique_expiries:
            try:
                opt_chain = ticker_obj.option_chain(expiry)
                expiry_data[expiry] = {
                    'calls': opt_chain.calls,
                    'puts': opt_chain.puts
                }
            except Exception as e:
                print(f"Error fetching option chain for {ticker} {expiry}: {e}")
        
        # Extract current prices
        results = []
        for opt in options_list:
            expiry = opt.get('expiry')
            strike = opt.get('strike')
            opt_type = opt.get('type', 'call').lower()
            
            current_price = None
            if expiry in expiry_data:
                chain_df = expiry_data[expiry]['calls' if opt_type == 'call' else 'puts']
                current_price = _extract_price_from_chain(chain_df, strike)
            
            results.append({
                **opt,
                'current_price': current_price
            })
        
        return pd.DataFrame(results)
    except Exception as e:
        print(f"Error in get_batch_option_prices: {e}")
        return pd.DataFrame(options_list)


def get_platform_option_exposure(options_list: List[Dict]) -> Dict[str, float]:
    """Calculate option exposure by platform using real-time prices.
    
    Args:
        options_list: List of option trade dicts
        
    Returns:
        Dictionary mapping platform name to total option exposure
    """
    from db.db_utils import load_option_trades
    
    platform_exposure = {}
    
    if not options_list:
        return platform_exposure
    
    # Convert to DataFrame for easier processing
    opts_df = pd.DataFrame(options_list)
    
    if opts_df.empty:
        return platform_exposure
    
    # Extract option type from strategy
    opts_df['option_type'] = opts_df['strategy'].apply(lambda x: 'call' if 'call' in str(x).lower() else 'put')
    
    # Ensure numeric columns are float type (handle Decimal from database)
    opts_df['strike_price'] = pd.to_numeric(opts_df['strike_price'], errors='coerce')
    
    # Fetch current prices for all options grouped by ticker
    current_prices = {}
    for ticker in opts_df['ticker'].unique():
        ticker_opts = opts_df[opts_df['ticker'] == ticker].to_dict('records')
        options_list_for_ticker = [
            {
                'strike': float(t['strike_price']),
                'expiry': str(t['expiry_date']),
                'type': t['option_type']
            }
            for t in ticker_opts
        ]
        
        prices_df = get_batch_option_prices(ticker, options_list_for_ticker)
        for _, row in prices_df.iterrows():
            key = (ticker, float(row['strike']), str(row['expiry']), row['type'])
            current_prices[key] = row.get('current_price')
    
    # Apply current prices and calculate exposure
    opts_df['current_price'] = opts_df.apply(
        lambda row: current_prices.get(
            (row['ticker'], float(row['strike_price']), str(row['expiry_date']), row['option_type']),
            None
        ),
        axis=1
    )
    
    # Convert to numeric and calculate exposure
    opts_df['current_price'] = pd.to_numeric(opts_df['current_price'], errors='coerce')
    opts_df['transaction_type'] = opts_df['transaction_type'].str.lower()
    
    # Calculate exposure: current_price * 100 * (1 for debit, -1 for credit)
    opts_df['Option Exposure'] = opts_df.apply(
        lambda x: float(x['current_price'] or 0) * 100.0 * (1 if x['transaction_type'] == 'debit' else -1),
        axis=1
    )
    
    # Group by platform
    if 'Platform' in opts_df.columns:
        platform_exp = opts_df.groupby('Platform', as_index=False)['Option Exposure'].sum()
        for _, row in platform_exp.iterrows():
            platform_exposure[row['Platform'] or 'Unknown'] = float(row['Option Exposure'] or 0.0)
    
    return platform_exposure


def get_options_cost_basis(options_list: List[Dict]) -> Dict[str, float]:
    """
    Calculate cost basis (what you paid) for options grouped by platform.
    Cost Basis = option_open_price * 100 * (1 for debit, -1 for credit)
    
    Args:
        options_list: List of option trade dicts with keys: platform_id, option_open_price, transaction_type
    
    Returns:
        Dict mapping platform name to total cost basis for open options
    """
    if not options_list:
        return {}
    
    platform_cost_basis = {}
    
    # Get platform mapping
    from db.db_utils import load_option_trades
    platform_map = get_platform_id_to_name_map()
    
    # Convert to DataFrame for easier processing
    opts_df = pd.DataFrame(options_list)
    
    # Map platform IDs to names
    if 'platform_id' in opts_df.columns:
        opts_df['Platform'] = opts_df['platform_id'].map(platform_map)
    
    # Ensure numeric types
    opts_df['option_open_price'] = pd.to_numeric(opts_df.get('option_open_price', 0), errors='coerce').fillna(0)
    opts_df['transaction_type'] = opts_df['transaction_type'].str.lower()
    
    # Calculate cost basis: option_open_price * 100 * (1 for debit, -1 for credit)
    opts_df['Cost Basis'] = opts_df.apply(
        lambda x: float(x['option_open_price'] or 0) * 100.0 * (1 if x['transaction_type'] == 'debit' else -1),
        axis=1
    )
    
    # Group by platform
    if 'Platform' in opts_df.columns:
        platform_cb = opts_df.groupby('Platform', as_index=False)['Cost Basis'].sum()
        for _, row in platform_cb.iterrows():
            platform_cost_basis[row['Platform'] or 'Unknown'] = float(row['Cost Basis'] or 0.0)
    
    return platform_cost_basis


def get_options_portfolio_value(options_list: List[Dict]) -> Dict[str, float]:
    """
    Calculate current portfolio value for options grouped by platform using real-time prices.
    Portfolio Value = current_price * 100 * (1 for debit, -1 for credit)
    
    Args:
        options_list: List of option trade dicts with keys: platform_id, ticker, strike_price, expiry_date, option_type, transaction_type
    
    Returns:
        Dict mapping platform name to total current portfolio value for open options
    """
    if not options_list:
        return {}
    
    platform_portfolio_value = {}
    
    # Get platform mapping
    platform_map = get_platform_id_to_name_map()
    
    # Convert to DataFrame for easier processing
    opts_df = pd.DataFrame(options_list)
    
    # Map platform IDs to names
    if 'platform_id' in opts_df.columns:
        opts_df['Platform'] = opts_df['platform_id'].map(platform_map)
    
    # Extract option type and fetch current prices
    opts_df['option_type'] = opts_df['strategy'].apply(lambda x: 'call' if 'call' in str(x).lower() else 'put')
    
    # Fetch current prices for all options
    current_prices = {}
    for ticker in opts_df['ticker'].unique():
        ticker_opts = opts_df[opts_df['ticker'] == ticker].to_dict('records')
        options_list_for_ticker = [
            {
                'strike': t['strike_price'],
                'expiry': str(t['expiry_date']),
                'type': t['option_type']
            }
            for t in ticker_opts
        ]
        prices_df = get_batch_option_prices(ticker, options_list_for_ticker)
        for _, row in prices_df.iterrows():
            key = (ticker, row['strike'], str(row['expiry']), row['type'])
            current_prices[key] = row.get('current_price', 0)
    
    # Apply current prices
    opts_df['current_price'] = opts_df.apply(
        lambda row: current_prices.get(
            (row['ticker'], row['strike_price'], str(row['expiry_date']), row['option_type']),
            row.get('option_open_price', 0)  # fallback to open price
        ),
        axis=1
    )
    
    # Ensure numeric types
    opts_df['current_price'] = pd.to_numeric(opts_df['current_price'], errors='coerce').fillna(0)
    opts_df['transaction_type'] = opts_df['transaction_type'].str.lower()
    
    # Calculate portfolio value: current_price * 100 * (1 for debit, -1 for credit)
    opts_df['Portfolio Value'] = opts_df.apply(
        lambda x: float(x['current_price'] or 0) * 100.0 * (1 if x['transaction_type'] == 'debit' else -1),
        axis=1
    )
    
    # Group by platform
    if 'Platform' in opts_df.columns:
        platform_pv = opts_df.groupby('Platform', as_index=False)['Portfolio Value'].sum()
        for _, row in platform_pv.iterrows():
            platform_portfolio_value[row['Platform'] or 'Unknown'] = float(row['Portfolio Value'] or 0.0)
    
    return platform_portfolio_value
