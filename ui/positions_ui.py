import streamlit as st
from db.db_utils import load_positions, load_closed_positions, sync_positions_from_trades
from db.db_utils import PLATFORM_CACHE
import pandas as pd
from typing import Optional, List
import altair as alt

def _weighted_avg(df: pd.DataFrame, value_col: str, weight_col: str) -> float:
    """Compute weighted average for a DataFrame column."""
    return (df[value_col] * df[weight_col]).sum() / df[weight_col].sum() if df[weight_col].sum() else 0

def _drop_and_sort_columns(df: pd.DataFrame, drop_cols: List[str], sort_col: Optional[str] = None) -> pd.DataFrame:
    """Drop specified columns and sort by a column if provided."""
    for col in drop_cols:
        if col in df.columns:
            df = df.drop(columns=[col])
    if sort_col and sort_col in df.columns:
        df = df.sort_values(sort_col)
    return df

def get_positions_summary() -> pd.DataFrame:
    """Returns a summary DataFrame for open/closed positions and total P/L."""
    open_positions = load_positions()
    closed_positions = load_closed_positions()
    total_pnl = sum(p.get("profit_loss", 0.0) or 0.0 for p in closed_positions)
    return pd.DataFrame([{
        "Open Positions": len(open_positions),
        "Closed Positions": len(closed_positions),
        "Total P/L (Closed)": round(total_pnl, 2)
    }])

def positions_ui() -> None:
    """Streamlit UI for viewing positions. Adds grouped summary and collapsible details for open/closed positions by platform, with tickers grouped under each platform."""
    st.title("📋 Positions")
    if st.button("Sync Positions from Trades", help="Update open positions based on all trade data"):
        sync_positions_from_trades()
        st.success("Positions table synced with trades.")
        st.rerun()
    with st.spinner("Loading positions..."):
        positions = load_positions()
        closed_positions = load_closed_positions()
        st.subheader("🟢 Current Positions")
        if positions:
            df = pd.DataFrame(positions)
            if "platform_id" in df.columns:
                platform_map = {v: k for k, v in PLATFORM_CACHE.cache.items()}
                df["Platform"] = df["platform_id"].map(platform_map)
            for platform in sorted(df["Platform"].unique()):
                with st.expander(f"{platform} - Open Positions 📈", expanded=False):
                    platform_df = df[df["Platform"] == platform]
                    summary = (
                        platform_df
                        .groupby(["ticker"])
                        .apply(lambda g: pd.Series({
                            "Avg Entry Price": _weighted_avg(g, "entry_price", "quantity"),
                            "Total Quantity": g["quantity"].sum()
                        }), include_groups=False)
                        .reset_index()
                    )
                    summary = summary[["ticker", "Avg Entry Price", "Total Quantity"]]
                    st.markdown("**Summary by Ticker**")
                    st.dataframe(summary, use_width="stretch", hide_index=True)
                    # Restore bar chart: Open Positions by Ticker
                    chart = alt.Chart(summary).mark_bar().encode(
                        x=alt.X('ticker:N', title='Ticker'),
                        y=alt.Y('Total Quantity:Q', title='Quantity'),
                        color=alt.value('#59a14f')
                    )
                    st.altair_chart(chart, use_width="stretch")
                    st.markdown("**Detailed Positions**")
                    detail_df = _drop_and_sort_columns(platform_df.copy(), ["trade_type", "position_status", "platform_id", "id"], sort_col="entry_date")
                    st.dataframe(detail_df, use_width="stretch", hide_index=True)
        else:
            st.info("No open positions.")
        st.subheader("🔴 Closed Positions")
        if closed_positions:
            df_closed = pd.DataFrame(closed_positions)
            if "platform_id" in df_closed.columns:
                platform_map = {v: k for k, v in PLATFORM_CACHE.cache.items()}
                df_closed["Platform"] = df_closed["platform_id"].map(platform_map)
            for platform in sorted(df_closed["Platform"].unique()):
                with st.expander(f"{platform} - Closed Trades 📉", expanded=False):
                    platform_df = df_closed[df_closed["Platform"] == platform]
                    summary_closed = (
                        platform_df
                        .groupby("ticker")
                        .apply(lambda g: pd.Series({
                            "Avg Entry Price": _weighted_avg(g, "entry_price", "quantity"),
                            "Quantity": g["quantity"].sum(),
                            "Avg Exit Price": _weighted_avg(g, "exit_price", "quantity"),
                            "Profit/Loss": g["profit_loss"].sum()
                        }), include_groups=False)
                        .reset_index()
                    )
                    summary_closed = summary_closed[["ticker", "Avg Entry Price", "Quantity", "Avg Exit Price", "Profit/Loss"]]
                    st.markdown("**Summary by Ticker**")
                    highlight_cols = [col for col in summary_closed.columns if col.lower() in ["profit/loss"]]
                    if highlight_cols:
                        def color_profit_loss(val):
                            try:
                                v = float(str(val).replace('%',''))
                            except:
                                return ""
                            color = "green" if v > 0 else ("red" if v < 0 else "black")
                            return f"color: {color}"
                        styled_df = summary_closed.style.map(color_profit_loss, subset=highlight_cols)
                        st.dataframe(styled_df, use_width="stretch", hide_index=True)
                    else:
                        st.dataframe(summary_closed, use_width="stretch", hide_index=True)
                    # Restore bar chart: Closed Positions Profit/Loss by Ticker
                    chart = alt.Chart(summary_closed).mark_bar().encode(
                        x=alt.X('ticker:N', title='Ticker'),
                        y=alt.Y('Profit/Loss:Q', title='Total Profit/Loss'),
                        color=alt.value('#e15759')
                    )
                    st.altair_chart(chart, use_width="stretch")
                    st.markdown("**Detailed Closed Positions**")
                    detail_df = _drop_and_sort_columns(platform_df.copy(), ["trade_type", "position_status", "platform_id", "id"], sort_col="entry_date")
                    st.dataframe(detail_df, use_width="stretch", hide_index=True)
        else:
            st.info("No closed positions.")

