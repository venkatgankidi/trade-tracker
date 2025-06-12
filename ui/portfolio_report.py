import streamlit as st
import pandas as pd
import yfinance as yf
from db.db_utils import PLATFORM_CACHE
from sqlalchemy import text
from typing import Optional

def _get_portfolio_df() -> pd.DataFrame:
    """
    Returns a DataFrame with portfolio holdings, including current price and unrealized gain/loss.
    """
    conn = st.connection("postgresql", type="sql")
    query = """
SELECT platforms.name AS platform,
       ticker,
       SUM(CASE WHEN trade_type = 'Buy' THEN quantity ELSE -quantity END) AS total_quantity, 
       AVG(price) AS average_price,
       SUM(CASE WHEN trade_type = 'Buy' THEN price * quantity ELSE -price * quantity END) AS trade_cost
FROM trades
JOIN platforms ON trades.platform_id = platforms.id
GROUP BY platforms.name, ticker
    """
    with conn.session as session:
        result = session.execute(text(query))
        rows = result.fetchall()
        columns = ["platform", "ticker", "total_quantity", "average_price", "trade_cost"]
        portfolio_df = pd.DataFrame(rows, columns=columns)
    for col in ["total_quantity", "average_price", "trade_cost"]:
        if col in portfolio_df.columns:
            portfolio_df[col] = portfolio_df[col].astype(float)
    portfolio_df = portfolio_df[portfolio_df["total_quantity"] > 0]

    # Fetch current prices for each unique ticker only once
    unique_tickers = portfolio_df["ticker"].unique()
    ticker_price_map = {}
    for ticker in unique_tickers:
        try:
            price = yf.Ticker(ticker).history(period="1d", interval="1m")["Close"].iloc[-1]
            ticker_price_map[ticker] = price
        except Exception:
            ticker_price_map[ticker] = None
    portfolio_df["current_price"] = portfolio_df["ticker"].map(ticker_price_map)
    portfolio_df["current_value"] = portfolio_df["current_price"] * portfolio_df["total_quantity"]
    portfolio_df["unrealized_gain"] = portfolio_df["current_value"] - portfolio_df["trade_cost"]
    portfolio_df["percent_profit_loss"] = (portfolio_df["unrealized_gain"] / portfolio_df["trade_cost"]) * 100
    return portfolio_df

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
