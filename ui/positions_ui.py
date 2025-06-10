import streamlit as st
from db.db_utils import load_positions, insert_position, update_position, load_closed_positions, sync_positions_from_trades
from db.db_utils import PLATFORM_CACHE
import datetime
import pandas as pd
from typing import Optional

def get_positions_summary() -> pd.DataFrame:
    """
    Returns a summary DataFrame for open/closed positions and total P/L.
    """
    open_positions = load_positions()
    closed_positions = load_closed_positions()
    total_pnl = sum(p.get("profit_loss", 0.0) or 0.0 for p in closed_positions)
    return pd.DataFrame([{
        "Open Positions": len(open_positions),
        "Closed Positions": len(closed_positions),
        "Total P/L (Closed)": round(total_pnl, 2)
    }])

def positions_ui() -> None:
    """
    Streamlit UI for viewing positions. Only auto-filled tables are shown.
    """
    st.title("Positions")

    # Add sync button
    if st.button("Sync Positions from Trades", help="Update open positions based on all trade data"):
        sync_positions_from_trades()
        st.success("Positions table synced with trades.")
        st.rerun()

    positions = load_positions()

    # Profit/Loss Summary
    closed_positions = load_closed_positions()
    total_profit_loss = 0.0
    if closed_positions:
        total_profit_loss = sum(p.get("profit_loss", 0.0) or 0.0 for p in closed_positions)
    st.subheader(f"Total Profit/Loss (Closed Trades): {total_profit_loss:.2f}")

    def _format_gain(x: Optional[float]) -> str:
        color = "green" if x and x > 0 else "red"
        return f'<span style="color: {color}">{x:.2f}</span>' if x is not None else ""

    # Open Positions Table
    if positions:
        st.subheader("Current Positions")
        df = pd.DataFrame(positions)
        if "platform_id" in df.columns:
            platform_map = {v: k for k, v in PLATFORM_CACHE.cache.items()}
            df["Platform"] = df["platform_id"].map(platform_map)
            df = df.drop(columns=["platform_id"])
        # Remove trade_type and position_status from current positions table
        for col in ["trade_type", "position_status"]:
            if col in df.columns:
                df = df.drop(columns=[col])
        # Move Platform column next to Ticker if present
        if "Platform" in df.columns and "ticker" in df.columns:
            cols = list(df.columns)
            cols.insert(cols.index("ticker") + 1, cols.pop(cols.index("Platform")))
            df = df[cols]
        if "profit_loss" in df.columns:
            df["profit_loss"] = df["profit_loss"].apply(_format_gain)
        if "id" in df.columns:
            df = df.drop(columns=["id"])
        if "entry_date" in df.columns:
            df = df.sort_values("entry_date")
        st.markdown(df.to_html(escape=False, index=False), unsafe_allow_html=True)
    else:
        st.subheader("Current Positions")
        st.write("No data found.")

    # Closed Positions Table
    closed_positions = load_closed_positions()
    if closed_positions:
        st.subheader("Closed Trades")
        df_closed = pd.DataFrame(closed_positions)
        if "platform_id" in df_closed.columns:
            platform_map = {v: k for k, v in PLATFORM_CACHE.cache.items()}
            df_closed["Platform"] = df_closed["platform_id"].map(platform_map)
            df_closed = df_closed.drop(columns=["platform_id"])
        # Remove trade_type and position_status from closed positions table
        for col in ["trade_type", "position_status"]:
            if col in df_closed.columns:
                df_closed = df_closed.drop(columns=[col])
        # Move Platform column next to Ticker if present
        if "Platform" in df_closed.columns and "ticker" in df_closed.columns:
            cols = list(df_closed.columns)
            cols.insert(cols.index("ticker") + 1, cols.pop(cols.index("Platform")))
            df_closed = df_closed[cols]
        if "profit_loss" in df_closed.columns:
            df_closed["profit_loss"] = df_closed["profit_loss"].apply(_format_gain)
        if "id" in df_closed.columns:
            df_closed = df_closed.drop(columns=["id"])
        if "entry_date" in df_closed.columns:
            df_closed = df_closed.sort_values("entry_date")
        st.markdown(df_closed.to_html(escape=False, index=False), unsafe_allow_html=True)
    else:
        st.subheader("Closed Trades")
        st.write("No data found.")

