import streamlit as st
import pandas as pd
import yfinance as yf
from db.db_utils import PLATFORM_CACHE, load_positions
from sqlalchemy import text
from typing import Optional
import time

def _get_portfolio_df() -> pd.DataFrame:
    """
    Returns a DataFrame with portfolio holdings, including current price and unrealized gain/loss.
    Uses open positions for accurate trade cost.
    """
    # Use open positions for accurate trade cost
    open_positions = load_positions()
    if not open_positions:
        return pd.DataFrame(columns=["platform", "ticker", "total_quantity", "average_price", "trade_cost", "current_price", "current_value", "unrealized_gain", "percent_profit_loss"])
    df = pd.DataFrame(open_positions)
    platform_map = {v: k for k, v in PLATFORM_CACHE.cache.items()}
    df["platform"] = df["platform_id"].map(platform_map)
    summary = (
        df.groupby(["platform", "ticker"])
        .apply(lambda g: pd.Series({
            "total_quantity": g["quantity"].sum(),
            "average_price": (g["entry_price"] * g["quantity"]).sum() / g["quantity"].sum() if g["quantity"].sum() else 0,
            "trade_cost": (g["entry_price"] * g["quantity"]).sum()
        }))
        .reset_index()
    )
    # Fetch current prices for each unique ticker only once, cache for 5 min
    unique_tickers = summary["ticker"].unique()
    ticker_price_map = _get_ticker_prices(unique_tickers)
    summary["current_price"] = summary["ticker"].map(ticker_price_map)
    summary["current_value"] = summary["current_price"] * summary["total_quantity"]
    summary["unrealized_gain"] = summary["current_value"] - summary["trade_cost"]
    summary["percent_profit_loss"] = (summary["unrealized_gain"] / summary["trade_cost"]) * 100
    return summary

def get_position_summary() -> pd.DataFrame:
    """
    Returns a summary DataFrame for each platform (investment, value, unrealized gain).
    """
    portfolio_df = _get_portfolio_df()
    rows = []
    for platform in PLATFORM_CACHE.keys():
        group = portfolio_df[portfolio_df["platform"] == platform]
        if not group.empty:
            total_investment = group["trade_cost"].sum()
            total_portfolio_value = group["current_value"].sum()
            total_unrealized_gain = group["unrealized_gain"].sum()
            percent_unrealized = (total_unrealized_gain / total_investment * 100) if total_investment else 0.0
            rows.append({
                "Platform": platform,
                "Total Investment": round(total_investment, 2),
                "Total Portfolio Value": round(total_portfolio_value, 2),
                "Total Unrealized Gains": round(total_unrealized_gain, 2),
                "Pct Unrealized Gain": f"{round(percent_unrealized, 2)}%"
            })
    return pd.DataFrame(rows)

def get_position_summary_with_total() -> pd.DataFrame:
    """
    Returns the position summary with an additional total row.
    """
    summary_df = get_position_summary()
    if not summary_df.empty:
        total_investment = summary_df["Total Investment"].sum()
        total_value = summary_df["Total Portfolio Value"].sum()
        total_unrealized = summary_df["Total Unrealized Gains"].sum()
        percent_unrealized = (total_unrealized / total_investment * 100) if total_investment else 0.0
        overall_row = {
            "Platform": "Total",
            "Total Investment": round(total_investment, 2),
            "Total Portfolio Value": round(total_value, 2),
            "Total Unrealized Gains": round(total_unrealized, 2),
            "Pct Unrealized Gain": f"{round(percent_unrealized, 2)}%"
        }
        summary_df = pd.concat([summary_df, pd.DataFrame([overall_row])], ignore_index=True)
    return summary_df

def _format_gain(x: float) -> str:
    color = "green" if x > 0 else "red"
    return f'<span style="color: {color}">{x:.2f}</span>'

def _format_percent(x: float) -> str:
    color = "green" if x > 0 else "red"
    return f'<span style="color: {color}">{x:.2f}%</span>'

def portfolio_ui() -> None:
    """
    Streamlit UI for portfolio summary and holdings, with formatted output and error handling.
    """
    st.title("Portfolio")
    st.subheader("Portfolio Summary")
    summary_df = get_position_summary_with_total()
    if not summary_df.empty:
        st.dataframe(summary_df, use_container_width=True, hide_index=True)
    else:
        st.info("No positions found for summary.")
    portfolio_df = _get_portfolio_df()
    st.subheader("Portfolio Holdings")
    for platform, group_df in portfolio_df.groupby("platform"):
        st.write(f"Platform: {platform}")
        display_df = group_df.copy()
        display_df = display_df.sort_values("ticker")
        display_df = display_df.drop(columns=["platform"])

        # Show "Not available" for tickers with missing price
        display_df["current_price"] = display_df["current_price"].apply(
            lambda x: f'<span style="color: red">Not available</span>' if pd.isna(x) else f"${x:.2f}"
        )
        display_df["current_value"] = display_df.apply(
            lambda row: f'<span style="color: red">Not available</span>' if pd.isna(row["current_price"]) or row["current_price"] == '<span style="color: red">Not available</span>' else f"${row['current_value']:.2f}", axis=1
        )
        display_df["unrealized_gain"] = display_df.apply(
            lambda row: '<span style="color: red">Not available</span>' if "Not available" in str(row["current_value"]) else _format_gain(row["unrealized_gain"]), axis=1
        )
        display_df["percent_profit_loss"] = display_df.apply(
            lambda row: '<span style="color: red">Not available</span>' if "Not available" in str(row["current_value"]) else _format_percent(row["percent_profit_loss"]), axis=1
        )

        st.markdown(display_df.to_html(escape=False, index=False), unsafe_allow_html=True)

# Global cache for ticker prices
_TICKER_PRICE_CACHE = {}
_TICKER_PRICE_CACHE_TIME = 0
_TICKER_PRICE_CACHE_TTL = 300  # 5 minutes

def _get_ticker_prices(tickers):
    global _TICKER_PRICE_CACHE, _TICKER_PRICE_CACHE_TIME
    now = time.time()
    # Refresh cache if expired or missing tickers
    if (now - _TICKER_PRICE_CACHE_TIME > _TICKER_PRICE_CACHE_TTL) or not all(t in _TICKER_PRICE_CACHE for t in tickers):
        price_map = {}
        for ticker in tickers:
            try:
                price = yf.Ticker(ticker).history(period="1d", interval="1m")["Close"].iloc[-1]
                price_map[ticker] = price
            except Exception:
                price_map[ticker] = None
        _TICKER_PRICE_CACHE = price_map
        _TICKER_PRICE_CACHE_TIME = now
    return {t: _TICKER_PRICE_CACHE.get(t) for t in tickers}
