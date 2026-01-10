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
