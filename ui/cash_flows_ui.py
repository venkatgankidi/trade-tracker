import streamlit as st
import pandas as pd
import altair as alt
from db.db_utils import (
    load_cash_flows,
    PLATFORM_CACHE,
    insert_cash_flow,
    get_total_cash_by_platform
)
import datetime
from typing import Optional

def get_cash_flow_summary() -> pd.DataFrame:
    """Returns a summary DataFrame of deposits and withdrawals per platform and year."""
    cash_flows = load_cash_flows()
    if not cash_flows:
        return pd.DataFrame(columns=["Year", "Platform", "Total Deposits", "Total Withdrawals", "Net Cash"])
    
    df = pd.DataFrame(cash_flows)
    platform_map = {v: k for k, v in PLATFORM_CACHE.cache.items()}
    df["Platform"] = df["platform_id"].map(platform_map)
    df["flow_date"] = pd.to_datetime(df["flow_date"])
    df["Year"] = df["flow_date"].dt.year
    
    # Separate deposits and withdrawals
    deposits = df[df["flow_type"] == "deposit"].copy()
    withdrawals = df[df["flow_type"] == "withdrawal"].copy()
    
    # Group by year and platform
    dep_summary = deposits.groupby(["Year", "Platform"], as_index=False)["amount"].sum()
    dep_summary = dep_summary.rename(columns={"amount": "Total Deposits"})
    
    with_summary = withdrawals.groupby(["Year", "Platform"], as_index=False)["amount"].sum()
    with_summary = with_summary.rename(columns={"amount": "Total Withdrawals"})
    
    # Merge
    summary = pd.merge(dep_summary, with_summary, on=["Year", "Platform"], how="outer").fillna(0)
    summary["Net Cash"] = summary["Total Deposits"] - summary["Total Withdrawals"]
    
    return summary

def cash_flows_ui() -> None:
    """Streamlit UI for viewing cash flows by platform and year."""
    st.title("💰 Cash Deposits & Withdrawals")
    
    cash_flows = load_cash_flows()
    if not cash_flows:
        st.info("No cash flows recorded.")
        return
    
    df = pd.DataFrame(cash_flows)
    platform_map = {v: k for k, v in PLATFORM_CACHE.cache.items()}
    df["Platform"] = df["platform_id"].map(platform_map)
    df = df.drop(columns=["platform_id"], errors='ignore')
    
    st.subheader("📊 All Cash Flows")
    display_df = df[["flow_date", "Platform", "flow_type", "amount", "notes"]].copy()
    display_df.columns = ["Date", "Platform", "Type", "Amount", "Notes"]
    st.dataframe(display_df, width="stretch", hide_index=True)
    
    st.subheader("📈 Summary by Year and Platform")
    summary_df = get_cash_flow_summary()
    if not summary_df.empty:
        st.dataframe(summary_df, width="stretch", hide_index=True)
        
        # Chart: Net cash by year and platform
        melted = summary_df.melt(
            id_vars=["Year", "Platform"],
            value_vars=["Total Deposits", "Total Withdrawals", "Net Cash"],
            var_name="Type",
            value_name="Amount"
        )
        chart = alt.Chart(melted).mark_bar().encode(
            x=alt.X('Platform:N', title='Platform'),
            y=alt.Y('Amount:Q', title='Amount ($)'),
            color=alt.Color('Type:N', title='Type'),
            xOffset=alt.XOffset('Type:N')
        ).facet(
            column=alt.Column('Year:N', title='Year')
        ).properties(width=200)
        st.altair_chart(chart, use_container_width=True)

def cash_flows_data_entry() -> None:
    """Streamlit UI for manual entry of cash deposits and withdrawals (for Data Entry screen)."""
    st.subheader("➕ Record Cash Deposit/Withdrawal")
    
    with st.form("cash_flow_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        
        with col1:
            platform = st.selectbox(
                "Platform",
                list(PLATFORM_CACHE.keys()),
                help="Platform where the cash flow occurred."
            )
            flow_type = st.selectbox(
                "Type",
                ["deposit", "withdrawal"],
                help="Is this a deposit or withdrawal?"
            )
            amount = st.number_input(
                "Amount",
                min_value=0.0,
                format="%.2f",
                help="Amount of cash (positive value)."
            )
        
        with col2:
            flow_date = st.date_input(
                "Date",
                value=datetime.date.today(),
                help="Date of the cash flow."
            )
            notes = st.text_area(
                "Notes",
                help="Any additional notes about this cash flow."
            )
        
        submitted = st.form_submit_button("Record Cash Flow")
        
        if submitted:
            if amount <= 0:
                st.warning("Amount must be greater than zero.")
            else:
                platform_id = PLATFORM_CACHE.get(platform)
                if platform_id is None:
                    st.error("Invalid platform selected.")
                else:
                    with st.spinner("Recording cash flow..."):
                        insert_cash_flow(
                            platform_id=platform_id,
                            flow_type=flow_type,
                            amount=amount,
                            flow_date=flow_date,
                            notes=notes or None
                        )
                    st.toast(f"Cash {flow_type} recorded successfully!", icon="✅")
