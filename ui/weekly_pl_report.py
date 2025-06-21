import streamlit as st
import pandas as pd
import altair as alt
from db.db_utils import load_closed_positions, load_option_trades, PLATFORM_CACHE
import datetime

def get_weekly_pl_stocks():
    """Aggregate weekly profit/loss for stocks from closed positions."""
    closed_positions = load_closed_positions()
    if not closed_positions:
        return pd.DataFrame(columns=["Year", "Week", "Stock P/L"])
    df = pd.DataFrame(closed_positions)
    df = df.dropna(subset=["exit_date", "profit_loss"])
    df["exit_date"] = pd.to_datetime(df["exit_date"])
    df["Year"] = df["exit_date"].dt.year
    df["Week"] = df["exit_date"].dt.isocalendar().week
    weekly = df.groupby(["Year", "Week"], as_index=False)["profit_loss"].sum()
    weekly = weekly.rename(columns={"profit_loss": "Stock P/L"})
    return weekly

def get_weekly_pl_options():
    """Aggregate weekly profit/loss for options from closed option trades."""
    closed_options = [t for t in load_option_trades() if t.get("status") in ("closed", "expired", "exercised")]
    if not closed_options:
        return pd.DataFrame(columns=["Year", "Week", "Option P/L"])
    df = pd.DataFrame(closed_options)
    df = df.dropna(subset=["close_date", "profit_loss"])
    df["close_date"] = pd.to_datetime(df["close_date"])
    df["Year"] = df["close_date"].dt.year
    df["Week"] = df["close_date"].dt.isocalendar().week
    weekly = df.groupby(["Year", "Week"], as_index=False)["profit_loss"].sum()
    weekly = weekly.rename(columns={"profit_loss": "Option P/L"})
    return weekly

def weekly_pl_report_ui():
    st.title("📅 Weekly Profit/Loss Report (Stocks & Options)")
    st.markdown("Shows weekly P/L for both stocks and options, grouped by year and week.")

    stock_weekly = get_weekly_pl_stocks()
    option_weekly = get_weekly_pl_options()
    # Merge for combined table
    merged = pd.merge(stock_weekly, option_weekly, on=["Year", "Week"], how="outer").fillna(0)
    # Convert all to float using a robust approach (list comprehension)
    def to_float(x):
        try:
            return float(x)
        except Exception:
            return 0.0
    merged["Stock P/L"] = [to_float(x) for x in merged["Stock P/L"]]
    merged["Option P/L"] = [to_float(x) for x in merged["Option P/L"]]
    merged["Total P/L"] = merged["Stock P/L"] + merged["Option P/L"]
    merged = merged.sort_values(["Year", "Week"], ascending=[False, False])
    st.subheader("Weekly P/L Table")
    st.dataframe(merged, use_container_width=True, hide_index=True)

    st.subheader("Trending Graph: Weekly P/L")
    melted = merged.melt(id_vars=["Year", "Week"], value_vars=["Stock P/L", "Option P/L", "Total P/L"], var_name="Type", value_name="P/L")
    melted["Year-Week"] = melted["Year"].astype(str) + "-W" + melted["Week"].astype(str)
    chart = alt.Chart(melted).mark_line(point=True).encode(
        x=alt.X('Year-Week:N', title='Year-Week', sort=None, axis=alt.Axis(labelAngle=-45)),
        y=alt.Y('P/L:Q', title='Profit/Loss'),
        color=alt.Color('Type:N', title='Type'),
        tooltip=['Year', 'Week', 'Type', 'P/L']
    )
    st.altair_chart(chart, use_container_width=True)

    st.info("Green = profit, Red = loss. Data is based on closed trades only.")
