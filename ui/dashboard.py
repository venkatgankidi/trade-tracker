import streamlit as st
from ui.positions_ui import get_positions_manager_summary
from ui.portfolio_report import get_position_summary
from ui.option_trades_ui import get_option_trades_summary
from ui.taxes_ui import tax_summary

def dashboard():
    st.header("Dashboard")

    # Positions summary
    st.subheader("Positions Manager Summary")
    pos_mgr_df = get_positions_manager_summary()
    if not pos_mgr_df.empty:
        st.dataframe(pos_mgr_df, use_container_width=True, hide_index=True)
    else:
        st.info("No positions found for summary.")
    st.write("---")

    # Portfolio Summary
    st.subheader("Portfolio Summary")
    summary_df = get_position_summary()
    if not summary_df.empty:
        st.dataframe(summary_df, use_container_width=True, hide_index=True)
    else:
        st.info("No positions found for summary.")
    st.write("---")

    # Option Trades summary
    st.subheader("Option Trades Manager Summary")

    opt_df = get_option_trades_summary()
    if not opt_df.empty:
        st.dataframe(opt_df, use_container_width=True, hide_index=True)
    else:
        st.info("No option trades found for summary.")
    st.write("---")

    # Tax Summary (Yearly, no breakdown)
    st.subheader("Tax Summary by Year")
    summary_df = tax_summary()
    if not summary_df.empty:
        st.dataframe(summary_df, use_container_width=True, hide_index=True)
    else:
        st.info("No closed trades found for tax summary.")
