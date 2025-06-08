import streamlit as st
from db.db_utils import load_positions, load_closed_positions, load_option_trades

def dashboard():
    st.header("Dashboard")

    # Positions summary
    st.subheader("Positions Manager Summary")
    open_positions = load_positions()
    closed_positions = load_closed_positions()
    st.write(f"Open Positions: {len(open_positions)}")
    st.write(f"Closed Positions: {len(closed_positions)}")
    total_pnl = sum(p.get("profit_loss", 0.0) or 0.0 for p in closed_positions)
    st.write(f"Total P/L (Closed): {total_pnl:.2f}")
    st.write("---")

    # DCA Manager summary (reuse portfolio_report logic)
    st.subheader("DCA Manager Summary")
    from ui.portfolio_report import portfolio_summary
    portfolio_summary()
    st.write("---")

    # Option Trades summary
    st.subheader("Option Trades Manager Summary")
    open_options = load_option_trades(status="open")
    closed_options = load_option_trades(status="expired") + load_option_trades(status="exercised")
    st.write(f"Open Option Trades: {len(open_options)}")
    st.write(f"Closed Option Trades: {len(closed_options)}")
    total_option_pnl = sum(o.get("profit_loss", 0.0) or 0.0 for o in closed_options)
    st.write(f"Total Option P/L (Closed): {total_option_pnl:.2f}")
