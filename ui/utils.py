"""Shared utility functions for the trade tracker UI."""
import pandas as pd
from typing import Dict, List, Optional, Tuple
import yfinance as yf
import streamlit as st
from db.db_utils import PLATFORM_CACHE


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
        if option_type.lower() == 'call':
            chain_df = opt_chain.calls
        else:
            chain_df = opt_chain.puts
        
        # Find the option with matching strike
        matching = chain_df[chain_df['strike'] == strike]
        if matching.empty:
            return None
        
        # Get bid-ask midpoint for the current price
        bid = matching.iloc[0].get('bid', 0)
        ask = matching.iloc[0].get('ask', 0)
        
        # If both bid and ask are available, use midpoint
        if bid > 0 and ask > 0:
            return (bid + ask) / 2
        # Otherwise use the lastPrice if available
        elif bid > 0:
            return bid
        elif ask > 0:
            return ask
        else:
            return matching.iloc[0].get('lastPrice', None)
    except Exception as e:
        print(f"Error fetching option price for {ticker} {expiry} {strike} {option_type}: {e}")
        return None


def get_batch_option_prices(ticker: str, options_list: List[Dict]) -> pd.DataFrame:
    """Fetch current prices for multiple options of the same ticker.
    
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
                    'calls': opt_chain.calls.set_index('strike'),
                    'puts': opt_chain.puts.set_index('strike')
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
                if strike in chain_df.index:
                    row = chain_df.loc[strike]
                    bid = row.get('bid', 0)
                    ask = row.get('ask', 0)
                    if bid > 0 and ask > 0:
                        current_price = (bid + ask) / 2
                    elif bid > 0:
                        current_price = bid
                    elif ask > 0:
                        current_price = ask
                    else:
                        current_price = row.get('lastPrice', None)
            
            results.append({
                **opt,
                'current_price': current_price
            })
        
        return pd.DataFrame(results)
    except Exception as e:
        print(f"Error in get_batch_option_prices: {e}")
        return pd.DataFrame(options_list)
