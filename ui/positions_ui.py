import streamlit as st
from db.db_utils import load_positions, insert_position, update_position, load_closed_positions
import datetime

def positions_ui():
    st.title("Positions Manager")

    positions = load_positions()

    # Profit/Loss Summary
    closed_positions = load_closed_positions()
    total_profit_loss = 0.0
    if closed_positions:
        total_profit_loss = sum(p.get("profit_loss", 0.0) or 0.0 for p in closed_positions)
    st.subheader(f"Total Profit/Loss (Closed Trades): {total_profit_loss:.2f}")

    from utils.ui_helpers import render_table
    render_table(positions, title="Current Positions")
    closed_positions = load_closed_positions()
    render_table(closed_positions, title="Closed Trades")

    st.header("Add New Position")
    with st.form("add_position"):
        ticker = st.text_input("Ticker")
        position_type = st.selectbox("Position Type", ["LONG", "SHORT", "CLOSE"])
        entry_price = st.number_input("Entry Price", min_value=0.0, format="%.2f")
        quantity = st.number_input("Quantity", min_value=0.0, format="%.2f")
        entry_time = st.text_input("Entry Time", value=None, placeholder="YYYY-MM-DD HH:MM:SS")
        notes = st.text_area("Notes", value="")
        submitted = st.form_submit_button("Add Position")
        if submitted:
            insert_position(ticker, None, position_type, entry_price, quantity, entry_time, notes)
            from utils.ui_helpers import show_success
            show_success("Position added. Please refresh to see the update.")

    st.header("Update/Close Position")
    if positions:
        pos_ids = [p["id"] for p in positions]
        pos_id = st.selectbox("Select Position ID", pos_ids)
        selected = next((p for p in positions if p["id"] == pos_id), None)
        if selected:
            with st.form("update_position"):
                st.write(f"Ticker: {selected['ticker']}")
                st.write(f"Trade Type: {selected.get('trade_type', '')}")
                st.write(f"Entry Time: {selected['entry_time']}")
                new_position_type = st.selectbox("New Position Type", ["LONG", "SHORT", "CLOSE"], index=["LONG", "SHORT", "CLOSE"].index(selected["position_type"]))
                new_entry_price = st.number_input("New Entry Price", min_value=0.0, value=selected["entry_price"] or 0.0, format="%.2f")
                new_quantity = st.number_input("New Quantity", min_value=0.0, value=selected["quantity"] or 0.0, format="%.2f")
                new_notes = st.text_area("Notes", value=selected["notes"] or "")
                update_btn = st.form_submit_button("Update Position")
                close_btn = st.form_submit_button("Close (Delete) Position")
                if update_btn:
                    update_position(pos_id, position_type=new_position_type, entry_price=new_entry_price, quantity=new_quantity, notes=new_notes)
                    from utils.ui_helpers import show_success
                    show_success("Position updated. Please refresh to see the update.")
                if close_btn:
                    close_dialog(ticker=selected["ticker"], pos_id=pos_id)

@st.dialog("Close Position")
def close_dialog(ticker, pos_id):
    with st.form("close_position"):
        st.header("Close Position")
        st.write(f"Closing position for {ticker}")
        exit_price = st.number_input("Exit Price", min_value=0.0, format="%.2f", key=f"dialog_exit_price_{pos_id}")
        exit_time = st.text_input("Exit Time", value=None, placeholder="YYYY-MM-DD HH:MM:SS", key=f"dialog_exit_time_{pos_id}")
        confirm = st.form_submit_button("Confirm Close")
        if confirm:
            # Fetch entry_price, quantity, entry_time for profit/loss and trade_type calculation
            from db.db_utils import load_positions
            open_positions = load_positions()
            pos = next((p for p in open_positions if p["id"] == pos_id), None)
            entry_price = pos["entry_price"] if pos else 0.0
            quantity = pos["quantity"] if pos else 0.0
            entry_time = pos["entry_time"] if pos else None

            # Determine trade_type based on entry_time and exit_time
            trade_type = "swing"
            try:
                if entry_time and exit_time:
                    entry_dt = datetime.datetime.strptime(entry_time[:19], "%Y-%m-%d %H:%M:%S")
                    exit_dt = datetime.datetime.strptime(exit_time[:19], "%Y-%m-%d %H:%M:%S")
                    if entry_dt.date() == exit_dt.date():
                        trade_type = "day"
            except Exception:
                pass

            profit_loss = (exit_price - entry_price) * quantity
            update_position(pos_id, position_type="CLOSE", exit_price=exit_price, exit_time=exit_time, profit_loss=profit_loss, trade_type=trade_type)
            from utils.ui_helpers import show_success
            show_success(f"Position {pos_id} closed successfully. Profit/Loss: {profit_loss:.2f} (Trade Type: {trade_type})")

# Standalone execution removed; use app.py as the entry point.
