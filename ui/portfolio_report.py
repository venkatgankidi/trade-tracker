import streamlit as st
import pandas as pd
import yfinance as yf
from db.db_utils import PLATFORM_CACHE
from sqlalchemy import text

def _get_portfolio_df():
    conn = st.connection("postgresql", type="sql")
    query = """
SELECT platforms.name AS platform,
       ticker,
       SUM(CASE WHEN trade_type = 'Buy' THEN quantity ELSE -quantity END) AS total_quantity, 
       AVG(price) AS average_price,
       SUM(price * quantity) AS trade_cost
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
    portfolio_df["current_price"] = portfolio_df["ticker"].apply(lambda x: yf.Ticker(x).history(period="1d",interval = "1m")["Close"].iloc[-1])
    portfolio_df["current_value"] = portfolio_df["current_price"] * portfolio_df["total_quantity"]
    portfolio_df["unrealized_gain"] = portfolio_df["current_value"] - portfolio_df["trade_cost"]
    portfolio_df["percent_profit_loss"] = (portfolio_df["unrealized_gain"] / portfolio_df["trade_cost"]) * 100
    return portfolio_df

def portfolio_summary():
    st.subheader("Portfolio Summary")
    portfolio_df = _get_portfolio_df()
    for platform in PLATFORM_CACHE.keys():
        group = portfolio_df[portfolio_df["platform"] == platform]
        if not group.empty:
            st.write(f"Platform: {platform}")
            total_investment = group["trade_cost"].sum() 
            total_portfolio_value = group["current_value"].sum()
            total_unrealized_gain = group["unrealized_gain"].sum()
            st.write(f"  Total Investment: ${total_investment:.2f}")
            st.write(f"  Total Portfolio Value: ${total_portfolio_value:.2f}")
            st.write(f"  Total Unrealized Gains: ${total_unrealized_gain:.2f}")
            percent_unrealized = (total_unrealized_gain / total_investment * 100) if total_investment else 0.0
            st.write(f"  Pct Unrealized Gain: {percent_unrealized:.2f}%")

def _format_gain(x):
    color = "green" if x > 0 else "red"
    return f'<span style="color: {color}">{x:.2f}</span>'

def _format_percent(x):
    color = "green" if x > 0 else "red"
    return f'<span style="color: {color}">{x:.2f}%</span>'

def portfolio_report():
    portfolio_df = _get_portfolio_df()
    portfolio_summary()
    st.subheader("Portfolio Holdings")
    for platform, group_df in portfolio_df.groupby("platform"):
        st.write(f"Platform: {platform}")
        display_df = group_df.copy()
        display_df = display_df.sort_values("ticker")
        display_df = display_df.drop(columns=["platform"])
        display_df["unrealized_gain"] = display_df["unrealized_gain"].apply(_format_gain)
        display_df["percent_profit_loss"] = display_df["percent_profit_loss"].apply(_format_percent)
        st.markdown(display_df.to_html(escape=False, index=False), unsafe_allow_html=True)
