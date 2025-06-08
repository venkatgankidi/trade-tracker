import streamlit as st
from db.db_utils import PLATFORM_CACHE, insert_option_trade, load_option_trades, close_option_trade
import datetime

def option_trades_ui():
    st.title("Option Trades Manager")

    # Open Option Trades Table
    st.header("Open Option Trades")
    open_trades = load_option_trades(status="open")
    if open_trades:
        st.table(open_trades)
        trade_ids = [t["id"] for t in open_trades]
        trade_id = st.selectbox("Select Option Trade ID to Close", trade_ids)
        selected = next((t for t in open_trades if t["id"] == trade_id), None)
        if selected:
            with st.form("close_option_trade"):
                st.write(f"Ticker: {selected['ticker']}")
                st.write(f"Strategy: {selected['strategy']}")
                st.write(f"Trade Date: {selected['trade_date']}")
                st.write(f"Open Price: {selected['option_open_price']}")
                close_status = st.selectbox("Status", ["expired", "exercised"])
                close_date = st.date_input("Close Date", value=datetime.date.today())
                option_close_price = st.number_input("Option Close Price", min_value=0.0, format="%.2f")
                confirm = st.form_submit_button("Confirm Close")
                if confirm:
                    close_option_trade(trade_id, close_status, close_date, option_close_price)
                    st.success(f"Option trade {trade_id} closed as {close_status}.")
                    import time
                    time.sleep(2)
                    st.rerun()
    else:
        st.write("No open option trades.")

    # Closed Option Trades Table and Total P/L
    st.header("Closed Option Trades")
    closed_trades = load_option_trades(status="expired") + load_option_trades(status="exercised")
    if closed_trades:
        total_pnl = sum(t.get("profit_loss", 0.0) or 0.0 for t in closed_trades)
        st.subheader(f"Total Profit/Loss (Closed Option Trades): {total_pnl:.2f}")
        st.table(closed_trades)
    else:
        st.write("No closed option trades.")

    # Add Option Trade
    st.header("Add New Option Trade")
    with st.form("add_option_trade"):
        ticker = st.text_input("Ticker")
        platform = st.selectbox("Platform", list(PLATFORM_CACHE.keys()))
        strategy = st.selectbox("Option Strategy", [
            "call", "put", "cash secured put", "covered call", "straddle", "strangle", "vertical spread", "other"
        ])
        strike_price = st.number_input("Strike Price", min_value=0.0, format="%.2f")
        expiry_date = st.date_input("Expiry Date")
        trade_date = st.date_input("Trade Date", value=datetime.date.today())
        transaction_type = st.selectbox("Transaction Type", ["credit", "debit"])
        option_open_price = st.number_input("Option Open Price", min_value=0.0, format="%.2f")
        notes = st.text_area("Notes (optional)")
        submitted = st.form_submit_button("Add Option Trade")
        if submitted:
            insert_option_trade(
                ticker,
                PLATFORM_CACHE.get(platform),
                strategy,
                strike_price,
                expiry_date,
                trade_date,
                transaction_type,
                option_open_price,
                notes
            )
            st.success("Option trade added. Please refresh to see the update.")
            import time
            time.sleep(2)
            st.rerun()
