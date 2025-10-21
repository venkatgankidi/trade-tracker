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

def get_monthly_pl_stocks():
    """Aggregate monthly profit/loss for stocks from closed positions."""
    closed_positions = load_closed_positions()
    if not closed_positions:
        return pd.DataFrame(columns=["Year", "Month", "Stock P/L"])
    df = pd.DataFrame(closed_positions)
    df = df.dropna(subset=["exit_date", "profit_loss"])
    df["exit_date"] = pd.to_datetime(df["exit_date"])
    df["Year"] = df["exit_date"].dt.year
    df["Month"] = df["exit_date"].dt.month
    monthly = df.groupby(["Year", "Month"], as_index=False)["profit_loss"].sum()
    monthly = monthly.rename(columns={"profit_loss": "Stock P/L"})
    return monthly

def get_monthly_pl_options():
    """Aggregate monthly profit/loss for options from closed option trades."""
    closed_options = [t for t in load_option_trades() if t.get("status") in ("closed", "expired", "exercised")]
    if not closed_options:
        return pd.DataFrame(columns=["Year", "Month", "Option P/L"])
    df = pd.DataFrame(closed_options)
    df = df.dropna(subset=["close_date", "profit_loss"])
    df["close_date"] = pd.to_datetime(df["close_date"])
    df["Year"] = df["close_date"].dt.year
    df["Month"] = df["close_date"].dt.month
    monthly = df.groupby(["Year", "Month"], as_index=False)["profit_loss"].sum()
    monthly = monthly.rename(columns={"profit_loss": "Option P/L"})
    return monthly

def weekly_monthly_pl_report_ui():
    st.title("📊 Weekly & Monthly P/L Report")
    st.markdown("View your profit/loss trends by week and by month for both stocks and options.")

    # --- Weekly Table & Graph ---
    stock_weekly = get_weekly_pl_stocks()
    option_weekly = get_weekly_pl_options()
    merged_weekly = pd.merge(stock_weekly, option_weekly, on=["Year", "Week"], how="outer").fillna(0)
    def week_ending(year, week):
        return datetime.date.fromisocalendar(int(year), int(week), 7)
    merged_weekly["Stock P/L"] = [float(x) for x in merged_weekly["Stock P/L"]]
    merged_weekly["Option P/L"] = [float(x) for x in merged_weekly["Option P/L"]]
    merged_weekly["Total P/L"] = merged_weekly["Stock P/L"] + merged_weekly["Option P/L"]
    merged_weekly["Week Ending"] = [week_ending(row["Year"], row["Week"]) for _, row in merged_weekly.iterrows()]
    display_cols_week = ["Year", "Week Ending", "Stock P/L", "Option P/L", "Total P/L"]
    st.subheader("Weekly P/L Table")
    st.dataframe(merged_weekly[display_cols_week], use_width="stretch", hide_index=True)

    st.subheader("Weekly P/L Trend")
    melted_week = merged_weekly.melt(id_vars=["Year", "Week Ending"], value_vars=["Stock P/L", "Option P/L", "Total P/L"], var_name="Type", value_name="P/L")
    chart_week = alt.Chart(melted_week).mark_line(point=True).encode(
        x=alt.X('Week Ending:T', title='Week Ending', axis=alt.Axis(labelAngle=-45)),
        y=alt.Y('P/L:Q', title='Profit/Loss'),
        color=alt.Color('Type:N', title='Type'),
        tooltip=['Year', 'Week Ending', 'Type', 'P/L']
    )
    st.altair_chart(chart_week, use_width="stretch")

    # --- Monthly Table & Graph ---
    stock_monthly = get_monthly_pl_stocks()
    option_monthly = get_monthly_pl_options()
    merged_monthly = pd.merge(stock_monthly, option_monthly, on=["Year", "Month"], how="outer").fillna(0)
    merged_monthly["Stock P/L"] = [float(x) for x in merged_monthly["Stock P/L"]]
    merged_monthly["Option P/L"] = [float(x) for x in merged_monthly["Option P/L"]]
    merged_monthly["Total P/L"] = merged_monthly["Stock P/L"] + merged_monthly["Option P/L"]
    merged_monthly["Month Name"] = merged_monthly["Month"].apply(lambda m: datetime.date(1900, int(m), 1).strftime('%b'))
    display_cols_month = ["Year", "Month Name", "Stock P/L", "Option P/L", "Total P/L"]
    st.subheader("Monthly P/L Table")
    st.dataframe(merged_monthly[display_cols_month], use_width="stretch", hide_index=True)

    st.subheader("Monthly P/L Trend")
    melted_month = merged_monthly.melt(id_vars=["Year", "Month Name"], value_vars=["Stock P/L", "Option P/L", "Total P/L"], var_name="Type", value_name="P/L")
    chart_month = alt.Chart(melted_month).mark_line(point=True).encode(
        x=alt.X('Month Name:N', title='Month', sort=list(['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'])),
        y=alt.Y('P/L:Q', title='Profit/Loss'),
        color=alt.Color('Type:N', title='Type'),
        tooltip=['Year', 'Month Name', 'Type', 'P/L']
    ).facet(
        column=alt.Column('Year:N', title='Year')
    )
    st.altair_chart(chart_month, use_width="stretch")
