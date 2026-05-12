import streamlit as st
from db.db_utils import load_positions, load_closed_positions, sync_positions_from_trades
from db.db_utils import PLATFORM_CACHE
import pandas as pd
from typing import Optional, List
import altair as alt
from ui.utils import get_platform_id_to_name_map, color_profit_loss

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
    long_open = sum(1 for p in open_positions if (p.get("direction") or "Long") == "Long")
    short_open = sum(1 for p in open_positions if (p.get("direction") or "Long") == "Short")
    return pd.DataFrame([{
        "Open Positions (🔼 Long)": long_open,
        "Open Positions (🔻 Short)": short_open,
        "Closed Positions": len(closed_positions),
        "Total P/L (Closed)": round(total_pnl, 2)
    }])

def _render_open_positions_for_direction(platform_df: pd.DataFrame, direction: str) -> None:
    """Render open position summary and chart for a given direction (Long or Short)."""
    dir_df = platform_df[platform_df["direction"] == direction]
    if dir_df.empty:
        return
    label = "🔼 Long" if direction == "Long" else "🔻 Short"
    bar_color = "#59a14f" if direction == "Long" else "#e15759"
    st.markdown(f"**{label} Positions**")
    summary = (
        dir_df
        .groupby(["ticker"])
        .apply(lambda g: pd.Series({
            "Avg Entry Price": _weighted_avg(g, "entry_price", "quantity"),
            "Total Quantity": g["quantity"].sum()
        }), include_groups=False)
        .reset_index()
    )
    summary = summary[["ticker", "Avg Entry Price", "Total Quantity"]]
    st.dataframe(summary, width="stretch", hide_index=True)
    chart = alt.Chart(summary).mark_bar().encode(
        x=alt.X('ticker:N', title='Ticker'),
        y=alt.Y('Total Quantity:Q', title='Quantity'),
        color=alt.value(bar_color)
    )
    st.altair_chart(chart)
    st.markdown("**Detailed Positions**")
    detail_df = _drop_and_sort_columns(
        dir_df.copy(),
        ["trade_type", "position_status", "platform_id", "id", "direction"],
        sort_col="entry_date"
    )
    st.dataframe(detail_df, width="stretch", hide_index=True)

def positions_ui() -> None:
    """
    Streamlit UI for viewing positions.
    Long and Short positions are shown in separate subsections per platform.
    """
    st.title("📋 Positions")
    if st.button("Sync Positions from Trades", help="Update open positions based on all trade data"):
        sync_positions_from_trades()
        st.success("Positions table synced with trades.")
        st.rerun()
    with st.spinner("Loading positions..."):
        positions = load_positions()
        closed_positions = load_closed_positions()

        # --- Open Positions ---
        st.subheader("🟢 Current Positions")
        if positions:
            df = pd.DataFrame(positions)
            # Ensure direction column exists; default to Long for legacy rows
            if "direction" not in df.columns:
                df["direction"] = "Long"
            else:
                df["direction"] = df["direction"].fillna("Long")
            if "platform_id" in df.columns:
                platform_map = get_platform_id_to_name_map()
                df["Platform"] = df["platform_id"].map(platform_map)
            for platform in sorted(df["Platform"].unique()):
                platform_df = df[df["Platform"] == platform]
                has_long = not platform_df[platform_df["direction"] == "Long"].empty
                has_short = not platform_df[platform_df["direction"] == "Short"].empty
                if has_long and has_short:
                    icon = "🔼🔻"
                elif has_short:
                    icon = "🔻"
                else:
                    icon = "🔼"
                with st.expander(f"{platform} - Open Positions {icon}", expanded=False):
                    _render_open_positions_for_direction(platform_df, "Long")
                    _render_open_positions_for_direction(platform_df, "Short")
        else:
            st.info("No open positions.")

        # --- Closed Positions ---
        st.subheader("🔴 Closed Positions")
        if closed_positions:
            df_closed = pd.DataFrame(closed_positions)
            if "direction" not in df_closed.columns:
                df_closed["direction"] = "Long"
            else:
                df_closed["direction"] = df_closed["direction"].fillna("Long")
            if "platform_id" in df_closed.columns:
                platform_map = get_platform_id_to_name_map()
                df_closed["Platform"] = df_closed["platform_id"].map(platform_map)
            for platform in sorted(df_closed["Platform"].unique()):
                with st.expander(f"{platform} - Closed Trades 📉", expanded=False):
                    platform_df = df_closed[df_closed["Platform"] == platform]
                    summary_closed = (
                        platform_df
                        .groupby(["ticker", "direction"])
                        .apply(lambda g: pd.Series({
                            "Avg Entry Price": _weighted_avg(g, "entry_price", "quantity"),
                            "Quantity": g["quantity"].sum(),
                            "Avg Exit Price": _weighted_avg(g, "exit_price", "quantity"),
                            "Profit/Loss": g["profit_loss"].sum()
                        }), include_groups=False)
                        .reset_index()
                    )
                    # Human-readable direction badge
                    summary_closed["Direction"] = summary_closed["direction"].apply(
                        lambda d: "🔼 Long" if d == "Long" else "🔻 Short"
                    )
                    summary_closed = summary_closed[[
                        "ticker", "Direction", "Avg Entry Price", "Quantity", "Avg Exit Price", "Profit/Loss"
                    ]]
                    st.markdown("**Summary by Ticker & Direction**")
                    highlight_cols = [col for col in summary_closed.columns if col.lower() in ["profit/loss"]]
                    if highlight_cols:
                        styled_df = summary_closed.style.map(color_profit_loss, subset=highlight_cols)
                        st.dataframe(styled_df, width="stretch", hide_index=True)
                    else:
                        st.dataframe(summary_closed, width="stretch", hide_index=True)
                    # Bar chart coloured by direction
                    chart = alt.Chart(summary_closed).mark_bar().encode(
                        x=alt.X('ticker:N', title='Ticker'),
                        y=alt.Y('Profit/Loss:Q', title='Total Profit/Loss'),
                        color=alt.Color('Direction:N', scale=alt.Scale(
                            domain=["🔼 Long", "🔻 Short"],
                            range=["#59a14f", "#e15759"]
                        )),
                        tooltip=['ticker:N', 'Direction:N', 'Profit/Loss:Q']
                    )
                    st.altair_chart(chart)
                    st.markdown("**Detailed Closed Positions**")
                    detail_df = _drop_and_sort_columns(
                        platform_df.copy(),
                        ["trade_type", "position_status", "platform_id", "id"],
                        sort_col="entry_date"
                    )
                    st.dataframe(detail_df, width="stretch", hide_index=True)
        else:
            st.info("No closed positions.")
