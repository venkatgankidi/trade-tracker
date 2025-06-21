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
    # Add week range column (e.g., '2025-06-16 to 2025-06-22')
    def week_range(year, week):
        # ISO week: Monday is the first day of the week
        d = datetime.date.fromisocalendar(int(year), int(week), 1)
        week_start = d
        week_end = d + datetime.timedelta(days=6)
        return f"{week_start.strftime('%Y-%m-%d')} to {week_end.strftime('%Y-%m-%d')}"
    merged["Week Range"] = [week_range(row["Year"], row["Week"]) for _, row in merged.iterrows()]
    # Reorder columns for display
    display_cols = ["Week Range", "Stock P/L", "Option P/L", "Total P/L"]
    st.subheader("Weekly P/L Table")
    st.dataframe(merged[display_cols], use_container_width=True, hide_index=True)

    st.subheader("Trending Graph: Weekly P/L")
    melted = merged.melt(id_vars=["Week Range"], value_vars=["Stock P/L", "Option P/L", "Total P/L"], var_name="Type", value_name="P/L")
    chart = alt.Chart(melted).mark_line(point=True).encode(
        x=alt.X('Week Range:N', title='Week Range', sort=None, axis=alt.Axis(labelAngle=-45)),
        y=alt.Y('P/L:Q', title='Profit/Loss'),
        color=alt.Color('Type:N', title='Type'),
        tooltip=['Week Range', 'Type', 'P/L']
    )
    st.altair_chart(chart, use_container_width=True)

    st.info("Green = profit, Red = loss. Data is based on closed trades only.")
