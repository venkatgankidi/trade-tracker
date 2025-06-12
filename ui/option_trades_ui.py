import streamlit as st
from db.db_utils import PLATFORM_CACHE, insert_option_trade, load_option_trades, close_option_trade
import datetime
import pandas as pd
from typing import Optional

def get_option_trades_summary() -> pd.DataFrame:
    """
    Returns a summary DataFrame for option trades (open/closed count and total P/L).
    """
    open_trades = load_option_trades(status="open")
    closed_trades = load_option_trades(status="expired") + load_option_trades(status="exercised") + load_option_trades(status="close")
    total_pnl = sum(t.get("profit_loss", 0.0) or 0.0 for t in closed_trades)
    return pd.DataFrame([{
        "Open Option Trades": len(open_trades),
        "Closed Option Trades": len(closed_trades),
        "Total Option P/L (Closed)": round(total_pnl, 2)
    }])

def option_trades_ui() -> None:
    """
    Streamlit UI for viewing option trades. No data entry or closing form here.
    """
    st.title("Option Trades")

    # Total Profit/Loss for Closed Option Trades
    closed_trades = (
        load_option_trades(status="expired") +
        load_option_trades(status="exercised") +
        load_option_trades(status="close")
    )
    total_pnl = sum(t.get("profit_loss", 0.0) or 0.0 for t in closed_trades)
    st.subheader(f"Total Profit/Loss (Closed Option Trades): {total_pnl:.2f}")

    # Open Option Trades Table
    st.header("Open Option Trades")
    open_trades = load_option_trades(status="open")
    if open_trades:
        df_open = pd.DataFrame(open_trades)
        # Map platform_id to platform name
        if "platform_id" in df_open.columns:
            platform_map = {v: k for k, v in PLATFORM_CACHE.cache.items()}
            df_open["platform"] = df_open["platform_id"].map(platform_map)
            df_open = df_open.drop(columns=["platform_id"])
        # Move open_fee next to option_open_price
        cols = list(df_open.columns)
        if "option_open_price" in cols and "open_fee" in cols:
            open_price_idx = cols.index("option_open_price")
            fee_idx = cols.index("open_fee")
            if abs(open_price_idx - fee_idx) > 1:
                cols.remove("open_fee")
                cols.insert(open_price_idx + 1, "open_fee")
            df_open = df_open[cols]
        # Remove closing-related columns
        for col in ["option_close_price", "close_fee", "profit_loss", "status", "close_date"]:
            if col in df_open.columns:
                df_open = df_open.drop(columns=[col])
        st.markdown(df_open.to_html(escape=False, index=False), unsafe_allow_html=True)
    else:
        st.write("No open option trades.")

    # Closed Option Trades Table and Total P/L
    st.header("Closed Option Trades")
    closed_trades = (
        load_option_trades(status="expired") +
        load_option_trades(status="exercised") +
        load_option_trades(status="close")
    )
    if closed_trades:
        total_pnl = sum(t.get("profit_loss", 0.0) or 0.0 for t in closed_trades)
        st.subheader(f"Total Profit/Loss (Closed Option Trades): {total_pnl:.2f}")
        df_closed = pd.DataFrame(closed_trades)
        # Map platform_id to platform name
        if "platform_id" in df_closed.columns:
            platform_map = {v: k for k, v in PLATFORM_CACHE.cache.items()}
            df_closed["platform"] = df_closed["platform_id"].map(platform_map)
            df_closed = df_closed.drop(columns=["platform_id"])
        if "profit_loss" in df_closed.columns:
            df_closed["profit_loss"] = df_closed["profit_loss"].apply(_format_gain)
        if "id" in df_closed.columns:
            df_closed = df_closed.drop(columns=["id"])
        if "entry_date" in df_closed.columns:
            df_closed = df_closed.sort_values("entry_date")
        st.markdown(df_closed.to_html(escape=False, index=False), unsafe_allow_html=True)
    else:
        st.write("No closed option trades.")

    def _format_gain(x: Optional[float]) -> str:
        color = "green" if x and x > 0 else "red"
        return f'<span style="color: {color}">{x:.2f}</span>' if x is not None else ""

def option_trades_data_entry():
    """
    Streamlit UI for adding new option trades only (for Data Entry screen).
    """
    st.subheader("Add New Option Trade")
    with st.form("add_option_trade", clear_on_submit=True):
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
        open_fee = st.number_input("Open Fee", min_value=0.0, format="%.2f", value=0.0)
        notes = st.text_area("Notes")
        submitted = st.form_submit_button("Add Option Trade")
        if submitted:
            if not ticker.strip():
                st.warning("Ticker cannot be empty.")
            elif strike_price <= 0 or option_open_price <= 0:
                st.warning("Strike price and open price must be greater than zero.")
            else:
                insert_option_trade(
                    ticker.strip().upper(),
                    PLATFORM_CACHE.get(platform),
                    strategy,
                    strike_price,
                    expiry_date,
                    trade_date,
                    transaction_type,
                    option_open_price,
                    notes,
                    open_fee
                )
                st.success("Option trade added. Please refresh to see the update.")
                import time
                time.sleep(2)
                st.rerun()
