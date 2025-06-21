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
    # Add year, month, and week ending date columns
    def week_ending(year, week):
        # ISO week: Monday is the first day, Sunday is the last (week ending)
        d = datetime.date.fromisocalendar(int(year), int(week), 7)
        return d
    merged["Year"] = merged["Year"].astype(int)
    merged["Month"] = [datetime.date.fromisocalendar(row["Year"], int(row["Week"]), 1).month for _, row in merged.iterrows()]
    merged["Week Ending"] = [week_ending(row["Year"], row["Week"]) for _, row in merged.iterrows()]
    # Reorder columns for display
    display_cols = ["Year", "Month", "Week Ending", "Stock P/L", "Option P/L", "Total P/L"]
    st.subheader("Weekly P/L Table (Year, Month, Week Ending)")
    st.dataframe(merged[display_cols], use_container_width=True, hide_index=True)

    st.subheader("Trending Graph: Weekly, Monthly, Yearly P/L")
    # Weekly trend
    melted_week = merged.melt(id_vars=["Year", "Month", "Week Ending"], value_vars=["Stock P/L", "Option P/L", "Total P/L"], var_name="Type", value_name="P/L")
    chart_week = alt.Chart(melted_week).mark_line(point=True).encode(
        x=alt.X('Week Ending:T', title='Week Ending', axis=alt.Axis(labelAngle=-45)),
        y=alt.Y('P/L:Q', title='Profit/Loss'),
        color=alt.Color('Type:N', title='Type'),
        tooltip=['Year', 'Month', 'Week Ending', 'Type', 'P/L']
    ).properties(title="Weekly P/L Trend")
    st.altair_chart(chart_week, use_container_width=True)

    # Monthly trend
    monthly = merged.groupby(["Year", "Month"]).agg({"Stock P/L": "sum", "Option P/L": "sum", "Total P/L": "sum"}).reset_index()
    melted_month = monthly.melt(id_vars=["Year", "Month"], value_vars=["Stock P/L", "Option P/L", "Total P/L"], var_name="Type", value_name="P/L")
    chart_month = alt.Chart(melted_month).mark_line(point=True).encode(
        x=alt.X('Month:O', title='Month'),
        y=alt.Y('P/L:Q', title='Profit/Loss'),
        color=alt.Color('Type:N', title='Type'),
        tooltip=['Year', 'Month', 'Type', 'P/L']
    ).facet(
        column=alt.Column('Year:N', title='Year')
    ).properties(title="Monthly P/L Trend")
    st.altair_chart(chart_month, use_container_width=True)

    # Yearly trend
    yearly = merged.groupby(["Year"]).agg({"Stock P/L": "sum", "Option P/L": "sum", "Total P/L": "sum"}).reset_index()
    melted_year = yearly.melt(id_vars=["Year"], value_vars=["Stock P/L", "Option P/L", "Total P/L"], var_name="Type", value_name="P/L")
    chart_year = alt.Chart(melted_year).mark_bar().encode(
        x=alt.X('Year:O', title='Year'),
        y=alt.Y('P/L:Q', title='Profit/Loss'),
        color=alt.Color('Type:N', title='Type'),
        tooltip=['Year', 'Type', 'P/L']
    ).properties(title="Yearly P/L Trend")
    st.altair_chart(chart_year, use_container_width=True)

    st.info("Green = profit, Red = loss. Data is based on closed trades only.")
