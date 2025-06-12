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
    Streamlit UI for viewing positions. Adds grouped summary and collapsible details for open/closed positions by platform, with tickers grouped under each platform.
    """
    st.title("Positions")

    # Add sync button
    if st.button("Sync Positions from Trades", help="Update open positions based on all trade data"):
        sync_positions_from_trades()
        st.success("Positions table synced with trades.")
        st.rerun()

    positions = load_positions()
    closed_positions = load_closed_positions()

    # --- Summary by Platform (Open Positions) ---
    st.subheader("Current Positions")
    if positions:
        df = pd.DataFrame(positions)
        if "platform_id" in df.columns:
            platform_map = {v: k for k, v in PLATFORM_CACHE.cache.items()}
            df["Platform"] = df["platform_id"].map(platform_map)
        for platform in sorted(df["Platform"].unique()):
            with st.expander(f"{platform} - Open Positions", expanded=False):
                platform_df = df[df["Platform"] == platform]
                # Summary by ticker for this platform
                summary = platform_df.groupby(["ticker"]).agg({
                    "quantity": "sum",
                    "entry_price": "mean"
                }).reset_index()
                summary = summary.rename(columns={"quantity": "Total Quantity", "entry_price": "Avg Entry Price"})
                st.markdown("**Summary by Ticker**")
                st.dataframe(summary, use_container_width=True, hide_index=True)
                # Detailed positions for this platform
                st.markdown("**Detailed Positions**")
                detail_df = platform_df.copy()
                for col in ["trade_type", "position_status", "platform_id"]:
                    if col in detail_df.columns:
                        detail_df = detail_df.drop(columns=[col])
                if "id" in detail_df.columns:
                    detail_df = detail_df.drop(columns=["id"])
                if "entry_date" in detail_df.columns:
                    detail_df = detail_df.sort_values("entry_date")
                st.dataframe(detail_df, use_container_width=True, hide_index=True)
    else:
        st.write("No open positions found.")

    # --- Summary by Platform (Closed Positions) ---
    st.subheader("Closed Trades")
    if closed_positions:
        df_closed = pd.DataFrame(closed_positions)
        if "platform_id" in df_closed.columns:
            platform_map = {v: k for k, v in PLATFORM_CACHE.cache.items()}
            df_closed["Platform"] = df_closed["platform_id"].map(platform_map)
        for platform in sorted(df_closed["Platform"].unique()):
            with st.expander(f"{platform} - Closed Trades", expanded=False):
                platform_df = df_closed[df_closed["Platform"] == platform]
                # Summary by ticker for this platform, now includes fees
                summary_closed = platform_df.groupby(["ticker"]).agg({
                    "quantity": "sum",
                    "profit_loss": "sum",
                    "exit_price": "mean",
                    "open_fee": "sum",
                    "close_fee": "sum"
                }).reset_index()
                summary_closed["Total Fee"] = summary_closed["open_fee"] + summary_closed["close_fee"]
                summary_closed = summary_closed.rename(columns={
                    "quantity": "Total Quantity",
                    "profit_loss": "Total P/L",
                    "exit_price": "Avg Exit Price",
                    "open_fee": "Open Fee",
                    "close_fee": "Close Fee"
                })
                st.markdown("**Summary by Ticker**")
                st.dataframe(summary_closed, use_container_width=True, hide_index=True)
                # Detailed closed positions for this platform
                st.markdown("**Detailed Closed Positions**")
                detail_df = platform_df.copy()
                for col in ["trade_type", "position_status", "platform_id"]:
                    if col in detail_df.columns:
                        detail_df = detail_df.drop(columns=[col])
                if "id" in detail_df.columns:
                    detail_df = detail_df.drop(columns=["id"])
                if "entry_date" in detail_df.columns:
                    detail_df = detail_df.sort_values("entry_date")
                st.dataframe(detail_df, use_container_width=True, hide_index=True)
    else:
        st.write("No closed trades found.")

