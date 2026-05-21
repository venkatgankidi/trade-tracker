import streamlit as st
from ui.trade_form import trade_form
from ui.csv_upload import upload_csv
from ui.option_trades_ui import option_trades_data_entry
from ui.cash_flows_ui import cash_flows_data_entry
from db.db_utils import load_option_trades, close_option_trade, PLATFORM_CACHE, set_platform_cash_available, get_platform_cash_available_map
from db.db_utils import get_last_upload_time
from ui.utils import get_platform_id_to_name_map
import datetime
from typing import Optional, Dict, Any

def data_entry() -> None:
    """
    Streamlit UI for all data entry: manual trade, CSV upload, option trades, closing option trades, and cash flows.
    """
    st.title("📝 Data Entry")
    st.header("🛒 Manual Trade Entry")
    trade_form()
    st.markdown("---")
    st.header("📄 CSV Upload")
    # Show last CSV upload time (if any)
    last_upload_iso = get_last_upload_time()
    if last_upload_iso:
        try:
            # parse ISO UTC and display in local timezone
            dt = datetime.datetime.fromisoformat(last_upload_iso)
            # if naive assume UTC
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=datetime.timezone.utc).astimezone()
            local_str = dt.strftime("%Y-%m-%d %H:%M:%S %Z")
        except Exception:
            local_str = last_upload_iso
        st.caption(f"Last CSV upload: {local_str}")
    upload_csv()
    st.markdown("---")
    st.header("📑 Option Trades Data Entry")
    option_trades_data_entry()
    st.markdown("---")
    st.header("❌ Close Option Trade")
    open_trades = load_option_trades(status="open")
    if open_trades:
        platform_map = get_platform_id_to_name_map()
        def trade_label(trade: Dict[str, Any]) -> str:
            platform_name = platform_map.get(trade.get("platform_id"), "Unknown")
            qty = trade.get('quantity', 1) or 1
            qty_str = f" x{qty}" if qty > 1 else ""
            return f"{trade['id']} | {platform_name} | {trade['ticker']} | {trade['strategy'].title()}{qty_str}"
        trade_options = [(trade_label(t), t["id"]) for t in open_trades]
        selected = st.selectbox(
            "Select Option Trade to Close",
            trade_options,
            format_func=lambda x: x[0] if isinstance(x, tuple) else x,
            help="Choose the option trade you want to close.",
            key="close_option_trade_select"
        )
        trade_id = selected[1] if isinstance(selected, tuple) else None
        trade = next((t for t in open_trades if t["id"] == trade_id), None)
        if trade:
            # Show legs detail for multi-leg trades
            from db.db_utils import load_option_trade_legs
            from ui.option_strategies import is_multi_leg
            legs = load_option_trade_legs(trade_id) if is_multi_leg(trade.get('strategy', '')) else []

            with st.form("close_option_trade_data_entry", clear_on_submit=True):
                qty = trade.get('quantity', 1) or 1
                st.write(f"**Ticker:** {trade['ticker']}")
                st.write(f"**Strategy:** {trade['strategy'].title()}")
                st.write(f"**Trade Date:** {trade['trade_date']}")
                st.write(f"**Open Price (net per share):** {trade['option_open_price']}")
                st.write(f"**Contracts:** {qty}")
                if legs:
                    legs_str = " / ".join(
                        f"{lg['side'].upper()[:1]}${float(lg['strike_price']):.0f}{lg['leg_type'].upper()[:1]} @{float(lg['premium']):.2f}"
                        for lg in legs
                    )
                    st.write(f"**Legs:** {legs_str}")
                col1, col2 = st.columns(2)
                with col1:
                    close_status = st.selectbox("Status", ["expired", "exercised", "assigned", "closed"], help="Final status of the option trade.")
                    close_date = st.date_input("Close Date", value=datetime.date.today(), help="Date the option was closed.")
                with col2:
                    option_close_price = st.number_input("Close Price (net per share)", min_value=0.0, format="%.4f", help="Net premium per share to close. For expired trades, enter 0.")
                    close_fee = st.number_input("Close Fee", min_value=0.0, format="%.4f", value=0.0, help="Total fee paid to close the trade.")
                notes = st.text_area("Notes", value=trade.get("notes") or "", help="Any additional notes about this trade.")
                confirm = st.form_submit_button("Confirm Close")
                if confirm:
                    with st.spinner("Closing option trade..."):
                        close_option_trade(trade_id, close_status, close_date, option_close_price, notes, close_fee)
                        # If assigned or exercised, insert a stock transaction
                        # (only for single-leg strategies; multi-leg assignment is rare and manual)
                        if close_status in ("assigned", "exercised") and not legs:
                            from db.db_utils import insert_trade
                            ticker = trade['ticker']
                            platform_id = trade['platform_id']
                            strike_price = trade['strike_price']
                            trade_date = close_date
                            strategy = trade.get('strategy', '').lower()
                            # Determine trade_type based on strategy
                            if "cash secured put" in strategy or "covered call" in strategy:
                                trade_type = "Sell"
                            elif "call" in strategy or "put" in strategy:
                                trade_type = "Buy"
                            else:
                                trade_type = "Buy"  # Default fallback
                            insert_trade(
                                ticker=ticker,
                                platform_id=platform_id,
                                price=strike_price,
                                quantity=100.0 * qty,
                                date=trade_date,
                                trade_type=trade_type
                            )
                        st.toast(f"Option trade {trade_id} closed as {close_status}.", icon="✅")
    else:
        st.info("No open option trades to close.")
    st.markdown("---")
    st.header("🏦 Update Cash Available")
    # Platform list and current cash values
    platform_keys = list(PLATFORM_CACHE.keys())
    platform_cash_map = get_platform_cash_available_map()

    if platform_keys:
        # Selectbox outside form so it triggers rerun on platform change
        platform = st.selectbox("Platform", platform_keys, key="cash_available_platform")
        
        with st.form("update_cash_available_form", clear_on_submit=False):
            current = platform_cash_map.get(platform, 0.0)
            amount = st.number_input("Cash Available", value=float(current), format="%.2f")
            submitted = st.form_submit_button("Save Cash Available")
            if submitted:
                platform_id = PLATFORM_CACHE.get(platform)
                if platform_id is None:
                    st.error("Invalid platform selected.")
                else:
                    set_platform_cash_available(platform_id, amount)
                    st.success("Cash available updated.")
                    st.rerun()
    else:
        st.info("No platforms available to update cash available.")
    st.markdown("---")
    st.header("💰 Cash Deposits & Withdrawals")
    cash_flows_data_entry()

