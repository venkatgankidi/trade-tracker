import streamlit as st
from db.db_utils import PLATFORM_CACHE, insert_option_trade, load_option_trades
import datetime
import pandas as pd
from typing import Optional, List, Dict
import altair as alt

def _format_gain(x: Optional[float]) -> str:
    """Format gain/loss with color for display."""
    color = "green" if x and x > 0 else "red"
    return f'<span style="color: {color}">{x:.2f}</span>' if x is not None else ""

def _map_and_reorder_columns(df: pd.DataFrame, platform_map: Dict[int, str], drop_cols: List[str], move_cols: List[str]) -> pd.DataFrame:
    """Map platform_id to name, drop and reorder columns as needed."""
    if "platform_id" in df.columns:
        df["Platform"] = df["platform_id"].map(platform_map)
        df = df.drop(columns=["platform_id"], errors='ignore')
    if "id" in df.columns:
        df = df.drop(columns=["id"], errors='ignore')
    cols = list(df.columns)
    # Custom logic for open_fee after option_open_price
    if "open_fee" in cols and "option_open_price" in cols:
        cols.remove("open_fee")
        idx = cols.index("option_open_price")
        cols.insert(idx + 1, "open_fee")
    for col in move_cols:
        if col in cols and col not in ["open_fee"]:
            cols.insert(cols.index("ticker") + 1, cols.pop(cols.index(col)))
    for col in drop_cols:
        if col in df.columns:
            df = df.drop(columns=[col], errors='ignore')
    # Only keep columns that exist in the DataFrame
    return df[[c for c in cols if c in df.columns]]

def get_option_trades_summary() -> pd.DataFrame:
    """Returns a summary DataFrame for option trades (open/closed count and total P/L)."""
    open_trades = load_option_trades(status="open")
    closed_trades = load_option_trades(status="expired") + load_option_trades(status="exercised") + load_option_trades(status="closed")
    total_pnl = sum(t.get("profit_loss", 0.0) or 0.0 for t in closed_trades)
    return pd.DataFrame([{
        "Open Option Trades": len(open_trades),
        "Closed Option Trades": len(closed_trades),
        "Total Option P/L (Closed)": round(total_pnl, 2)
    }])

def option_trades_ui() -> None:
    """Streamlit UI for viewing option trades. No data entry or closing form here."""
    st.title("📈 Option Trades")
    platform_map = {v: k for k, v in PLATFORM_CACHE.cache.items()}
    with st.spinner("Loading option trades..."):
        closed_trades = (
            load_option_trades(status="expired") +
            load_option_trades(status="exercised") +
            load_option_trades(status="closed")
        )
        total_pnl = sum(t.get("profit_loss", 0.0) or 0.0 for t in closed_trades)
        st.subheader(f"💰 Total Profit/Loss (Closed Option Trades): {total_pnl:.2f}")
        st.header("🟢 Open Option Trades")
        open_trades = load_option_trades(status="open")
        if open_trades:
            df_open = pd.DataFrame(open_trades)
            df_open = _map_and_reorder_columns(
                df_open,
                platform_map,
                drop_cols=["option_close_price", "close_fee", "profit_loss", "status", "close_date","id"],
                move_cols=["Platform", "open_fee"]
            )
            # Highlight profit/loss columns if present
            highlight_cols = [col for col in df_open.columns if col in ["profit_loss"]]
            if highlight_cols:
                def color_profit_loss(val):
                    color = "green" if val > 0 else ("red" if val < 0 else "black")
                    return f"color: {color}"
                styled_df = df_open.style.map(color_profit_loss, subset=highlight_cols)
                st.dataframe(styled_df, use_container_width=True, hide_index=True)
            else:
                st.dataframe(df_open, use_container_width=True, hide_index=True)
        else:
            st.info("No open option trades.")
        st.header("🔴 Closed Option Trades")
        closed_trades = (
            load_option_trades(status="expired") +
            load_option_trades(status="exercised") +
            load_option_trades(status="closed")
        )
        if closed_trades:
            total_pnl = sum(t.get("profit_loss", 0.0) or 0.0 for t in closed_trades)
            st.subheader(f"💰 Total Profit/Loss (Closed Option Trades): {total_pnl:.2f}")
            df_closed = pd.DataFrame(closed_trades)
            df_closed = _map_and_reorder_columns(
                df_closed,
                platform_map,
                drop_cols=["id","status"],
                move_cols=["open_fee","Platform"]
            )
            # Reorder columns: close_fee, close_date before profit_loss and notes
            col_order = list(df_closed.columns)
            for col in ["close_fee", "close_date"]:
                if col in col_order:
                    col_order.remove(col)
            insert_idx = col_order.index("profit_loss") if "profit_loss" in col_order else len(col_order)
            col_order = col_order[:insert_idx] + ["close_fee", "close_date"] + col_order[insert_idx:]
            # Move notes after profit_loss
            if "notes" in col_order:
                col_order.remove("notes")
                profit_idx = col_order.index("profit_loss") if "profit_loss" in col_order else len(col_order)-1
                col_order.insert(profit_idx+1, "notes")
            df_closed = df_closed[[c for c in col_order if c in df_closed.columns]]
            # Highlight profit/loss columns if present
            highlight_cols = [col for col in df_closed.columns if col in ["profit_loss", "gain", "percentage"]]
            if highlight_cols:
                def color_profit_loss(val):
                    color = "green" if val > 0 else ("red" if val < 0 else "black")
                    return f"color: {color}"
                styled_df = df_closed.style.map(color_profit_loss, subset=highlight_cols)
                st.dataframe(styled_df, use_container_width=True, hide_index=True)
            else:
                st.dataframe(df_closed, use_container_width=True, hide_index=True)
            # Bar chart: Closed Option Trades P/L by Ticker (fix calculation)
            if 'ticker' in df_closed.columns and 'profit_loss' in df_closed.columns:
                # Ensure profit_loss is float and not multiplied
                df_closed['profit_loss'] = pd.to_numeric(df_closed['profit_loss'], errors='coerce').fillna(0)
                summary = df_closed.groupby('ticker', as_index=False)['profit_loss'].sum()
                chart = alt.Chart(summary).mark_bar().encode(
                    x=alt.X('ticker:N', title='Ticker'),
                    y=alt.Y('profit_loss:Q', title='Total Profit/Loss'),
                    color=alt.value('#f28e2b')
                )
                st.altair_chart(chart, use_container_width=True)
        else:
            st.info("No closed option trades.")

def option_trades_data_entry():
    """
    Streamlit UI for adding new option trades only (for Data Entry screen).
    """
    st.subheader("➕ Add New Option Trade")
    with st.form("add_option_trade", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            ticker = st.text_input("Ticker", help="Underlying symbol for the option.")
            platform = st.selectbox("Platform", list(PLATFORM_CACHE.keys()), help="Platform where the trade was executed.")
            strategy = st.selectbox("Option Strategy", [
                "call", "put", "cash secured put", "covered call"
            ], help="Type of option strategy.")
            strike_price = st.number_input("Strike Price", min_value=0.0, format="%.2f", help="Strike price of the option.")
            expiry_date = st.date_input("Expiry Date", help="Option expiry date.")
        with col2:
            trade_date = st.date_input("Trade Date", value=datetime.date.today(), help="Date the option trade was opened.")
            transaction_type = st.selectbox("Transaction Type", ["credit", "debit"], help="Credit or debit transaction.")
            option_open_price = st.number_input("Option Open Price", min_value=0.0, format="%.2f", help="Price at which the option was opened.")
            open_fee = st.number_input("Open Fee", min_value=0.0, format="%.2f", value=0.0, help="Fee paid to open the option.")
            notes = st.text_area("Notes", help="Any additional notes about this trade.")
        submitted = st.form_submit_button("Add Option Trade")
        if submitted:
            if not ticker.strip():
                st.warning("Ticker cannot be empty.")
            elif strike_price <= 0 or option_open_price <= 0:
                st.warning("Strike price and open price must be greater than zero.")
            else:
                with st.spinner("Adding option trade..."):
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
                st.toast("Option trade added! Please refresh to see the update.", icon="✅")
