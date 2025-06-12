import streamlit as st
from db.db_utils import load_positions, insert_position, update_position, load_closed_positions, sync_positions_from_trades
from db.db_utils import PLATFORM_CACHE
import datetime
import pandas as pd
from typing import Optional
from collections import defaultdict

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
    Streamlit UI for viewing positions. Adds grouped summary and collapsible details for open/closed positions.
    """
    st.title("Positions")

    # Add sync button
    if st.button("Sync Positions from Trades", help="Update open positions based on all trade data"):
        sync_positions_from_trades()
        st.success("Positions table synced with trades.")
        st.rerun()

    positions = load_positions()
    closed_positions = load_closed_positions()

    # --- Summary by Ticker and Platform (Open Positions) ---
    st.subheader("Current Positions")
    with st.expander("Summary by Ticker and Platform (Open Positions)", expanded=True):
        if positions:
            df = pd.DataFrame(positions)
            if "platform_id" in df.columns:
                platform_map = {v: k for k, v in PLATFORM_CACHE.cache.items()}
                df["Platform"] = df["platform_id"].map(platform_map)
            summary = df.groupby(["ticker", "Platform"]).agg({
                "quantity": "sum",
                "entry_price": "mean"
            }).reset_index()
            summary = summary.rename(columns={"quantity": "Total Quantity", "entry_price": "Avg Entry Price"})
            st.dataframe(summary, use_container_width=True, hide_index=True)
        else:
            st.write("No open positions found.")

    # --- Detailed Open Positions (Collapsible) ---
    with st.expander("Detailed Open Positions", expanded=False):
        if positions:
            df = pd.DataFrame(positions)
            if "platform_id" in df.columns:
                platform_map = {v: k for k, v in PLATFORM_CACHE.cache.items()}
                df["Platform"] = df["platform_id"].map(platform_map)
                df = df.drop(columns=["platform_id"])
            for col in ["trade_type", "position_status"]:
                if col in df.columns:
                    df = df.drop(columns=[col])
            if "id" in df.columns:
                df = df.drop(columns=["id"])
            if "entry_date" in df.columns:
                df = df.sort_values("entry_date")
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.write("No open positions found.")

    # --- Summary by Ticker and Platform (Closed Positions) ---
    st.subheader("Closed Trades")
    with st.expander("Summary by Ticker and Platform (Closed Positions)", expanded=True):
        if closed_positions:
            df_closed = pd.DataFrame(closed_positions)
            if "platform_id" in df_closed.columns:
                platform_map = {v: k for k, v in PLATFORM_CACHE.cache.items()}
                df_closed["Platform"] = df_closed["platform_id"].map(platform_map)
            summary_closed = df_closed.groupby(["ticker", "Platform"]).agg({
                "quantity": "sum",
                "profit_loss": "sum"
            }).reset_index()
            summary_closed = summary_closed.rename(columns={"quantity": "Total Quantity", "profit_loss": "Total P/L"})
            st.dataframe(summary_closed, use_container_width=True, hide_index=True)
        else:
            st.write("No closed trades found.")

    # --- Detailed Closed Positions (Collapsible) ---
    with st.expander("Detailed Closed Trades", expanded=False):
        if closed_positions:
            df_closed = pd.DataFrame(closed_positions)
            if "platform_id" in df_closed.columns:
                platform_map = {v: k for k, v in PLATFORM_CACHE.cache.items()}
                df_closed["Platform"] = df_closed["platform_id"].map(platform_map)
                df_closed = df_closed.drop(columns=["platform_id"])
            for col in ["trade_type", "position_status"]:
                if col in df_closed.columns:
                    df_closed = df_closed.drop(columns=[col])
            if "id" in df_closed.columns:
                df_closed = df_closed.drop(columns=["id"])
            if "entry_date" in df_closed.columns:
                df_closed = df_closed.sort_values("entry_date")
            st.dataframe(df_closed, use_container_width=True, hide_index=True)
        else:
            st.write("No closed trades found.")

