import streamlit as st
from ui.positions_ui import get_positions_summary
from ui.portfolio_report import get_position_summary_with_total, _get_portfolio_df
from ui.option_trades_ui import get_option_trades_summary
from ui.taxes_ui import tax_summary
import altair as alt
import pandas as pd
import yfinance as yf
from db.db_utils import PLATFORM_CACHE, load_option_trades
from typing import Dict

@st.cache_data(ttl=3600, show_spinner=False)
def _classify_ticker(ticker: str) -> str:
    """Return 'ETF' or 'Stock' using yfinance quoteType (cached)."""
    try:
        info = yf.Ticker(ticker).info
        qtype = (info.get("quoteType") or "").upper()
        return "ETF" if "ETF" in qtype else "Stock"
    except Exception:
        return "Stock"

@st.cache_data(ttl=300, show_spinner=False)
def compute_asset_allocation() -> pd.DataFrame:
    """
    Compute allocation per platform broken down into Stocks, ETFs, and Options.
    - Stocks/ETFs: sum of trade_cost from portfolio positions (entry_price * quantity)
    - Options: sum of abs(option_open_price * 100) for open option trades (assume 1 contract per record)
    """
    portfolio_df = _get_portfolio_df()  # from ui/portfolio_report.py
    rows = []
    if not portfolio_df.empty:
        # Determine asset type per ticker
        portfolio_df["Asset Type"] = portfolio_df["ticker"].apply(_classify_ticker)
        grp = portfolio_df.groupby(["platform", "Asset Type"], as_index=False)["trade_cost"].sum()
        for _, r in grp.iterrows():
            rows.append({
                "Platform": r["platform"],
                "Asset Type": r["Asset Type"],
                "Amount": float(r["trade_cost"] or 0.0)
            })
    
    # Options: approximate exposure from open option trades
    open_opts = load_option_trades(status="open")
    if open_opts:
        # map platform ids to names
        platform_map = {v: k for k, v in PLATFORM_CACHE.cache.items()}
        opts_df = pd.DataFrame(open_opts)
        if "platform_id" in opts_df.columns:
            opts_df["Platform"] = opts_df["platform_id"].map(platform_map)
        # compute premium * 100 per trade, debit positive/credit negative
        opts_df["option_open_price"] = pd.to_numeric(opts_df.get("option_open_price", 0), errors="coerce").fillna(0)
        opts_df["transaction_type"] = opts_df["transaction_type"].str.lower()
        # For debit trades (buy): positive amount, for credit trades (sell): negative amount
        opts_df["Option Exposure"] = opts_df.apply(
            lambda x: float(x["option_open_price"]) * 100.0 * (1 if x["transaction_type"] == "debit" else -1), 
            axis=1
        )
        opts_grp = opts_df.groupby("Platform", as_index=False)["Option Exposure"].sum()
        for _, r in opts_grp.iterrows():
            rows.append({
                "Platform": r["Platform"] or "Unknown",
                "Asset Type": "Options",
                "Amount": float(r["Option Exposure"] or 0.0)
            })
    
    if not rows:
        return pd.DataFrame(columns=["Platform", "Asset Type", "Amount"])
    return pd.DataFrame(rows)

def dashboard():
    st.header("📊 Dashboard")

    # --- Asset Allocation by Platform ---
    with st.spinner("Computing asset allocation..."):
        alloc_df = compute_asset_allocation()
        if not alloc_df.empty:
            st.subheader("📦 Asset Allocation by Platform")
            # Display table with amounts and percentages
            pivot = alloc_df.pivot_table(index="Platform", columns="Asset Type", values="Amount", aggfunc="sum", fill_value=0.0).reset_index()
            # Ensure columns order
            for col in ["Stock", "ETF", "Options"]:
                if col not in pivot.columns:
                    pivot[col] = 0.0
            
            # Calculate row totals and percentages
            pivot["Total"] = pivot[["Stock", "ETF", "Options"]].sum(axis=1)
            for col in ["Stock", "ETF", "Options"]:
                pivot[f"{col} %"] = (pivot[col] / pivot["Total"] * 100).round(2)
            
            # Organize columns for display
            amount_cols = ["Platform", "Stock", "ETF", "Options", "Total"]
            pct_cols = ["Platform", "Stock %", "ETF %", "Options %"]
            
            # Display amounts table
            st.write("Asset Amounts by Platform ($)")
            st.dataframe(pivot[amount_cols].round(2), use_container_width=True, hide_index=True)
            
            # Display percentages table
            st.write("Asset Distribution Percentages (%)")
            st.dataframe(pivot[pct_cols].round(2), use_container_width=True, hide_index=True)
            
            st.write("") # Add some spacing
            
            # Calculate percentages for each platform
            platforms = pivot["Platform"].unique()
            cols = st.columns(min(3, len(platforms)))  # Max 3 charts per row
            
            for idx, platform in enumerate(platforms):
                platform_data = pivot[pivot["Platform"] == platform]
                total = platform_data[["Stock", "ETF", "Options"]].sum(axis=1).iloc[0]
                
                if total > 0:  # Only show pie chart if there are assets
                    pie_data = []
                    for asset_type in ["Stock", "ETF", "Options"]:
                        value = platform_data[asset_type].iloc[0]
                        percentage = (value / total * 100) if total > 0 else 0
                        if value != 0:  # Only include non-zero values
                            pie_data.append({
                                "Asset Type": asset_type,
                                "Amount": value,
                                "Percentage": percentage
                            })
                    
                    pie_df = pd.DataFrame(pie_data)
                    if not pie_df.empty:
                        with cols[idx % 3]:
                            # Create the base pie chart
                            pie_chart = alt.Chart(pie_df).mark_arc(innerRadius=50).encode(
                                theta=alt.Theta(field="Amount", type="quantitative", stack=True),
                                color=alt.Color(
                                    field="Asset Type",
                                    type="nominal",
                                    legend=alt.Legend(
                                        title="Asset Types",
                                        orient="bottom",
                                        labelFontSize=11,
                                        titleFontSize=12,
                                        columns=3
                                    )
                                ),
                                tooltip=[
                                    alt.Tooltip("Asset Type:N"),
                                    alt.Tooltip("Amount:Q", format="$,.2f"),
                                    alt.Tooltip("Percentage:Q", format=".1f", title="Percentage (%)")
                                ]
                            ).properties(
                                width=300,
                                height=300,
                                title=alt.TitleParams(
                                    text=f"{platform}",
                                    anchor="middle",
                                    fontSize=16,
                                    dy=-10
                                )
                            )
                            
                            # Add percentage and amount labels with improved visibility
                            labels = alt.Chart(pie_df).mark_text(
                                radius=90,
                                size=11,
                                fontWeight='bold',
                                baseline='middle'
                            ).encode(
                                theta=alt.Theta(field="Amount", type="quantitative", stack=True),
                                text=alt.Text("Percentage:Q", format=".1f"),
                                color=alt.value("white")
                            )
                            
                            # Create combined visualization
                            st.altair_chart(pie_chart + labels, use_container_width=True)
        else:
            st.info("No portfolio or option data available to compute allocation.")

    with st.spinner("Loading positions summary..."):
        st.subheader("📈 Positions Summary")
        pos_mgr_df = get_positions_summary()
        if not pos_mgr_df.empty:
            highlight_cols = [col for col in pos_mgr_df.columns if col.lower() in ["profit_loss", "gain", "total p/l (closed)", "pct_unrealized_gain"]]
            if highlight_cols:
                def color_profit_loss(val):
                    try:
                        v = float(str(val).replace('%',''))
                    except:
                        return ""
                    color = "green" if v > 0 else ("red" if v < 0 else "black")
                    return f"color: {color}"
                styled_df = pos_mgr_df.style.map(color_profit_loss, subset=highlight_cols)
                st.dataframe(styled_df, use_container_width=True, hide_index=True)
            else:
                st.dataframe(pos_mgr_df, use_container_width=True, hide_index=True)
        else:
            st.info("No positions found for summary.")
    st.markdown("---")

    with st.spinner("Loading portfolio summary..."):
        st.subheader("💼 Portfolio Summary")
        summary_df = get_position_summary_with_total()
        if not summary_df.empty:
            highlight_cols = [col for col in summary_df.columns if col.lower() in ["total unrealized gains", "pct unrealized gain"]]
            if highlight_cols:
                def color_profit_loss(val):
                    try:
                        v = float(str(val).replace('%',''))
                    except:
                        return ""
                    color = "green" if v > 0 else ("red" if v < 0 else "black")
                    return f"color: {color}"
                styled_df = summary_df.style.map(color_profit_loss, subset=highlight_cols)
                st.dataframe(styled_df, use_container_width=True, hide_index=True)
            else:
                st.dataframe(summary_df, use_container_width=True, hide_index=True)
        else:
            st.info("No positions found for summary.")
    st.markdown("---")

    with st.spinner("Loading option trades summary..."):
        st.subheader("📝 Option Trades Summary")
        opt_df = get_option_trades_summary()
        if not opt_df.empty:
            highlight_cols = [col for col in opt_df.columns if col.lower() in ["profit_loss", "gain", "total option p/l (closed)"]]
            if highlight_cols:
                def color_profit_loss(val):
                    try:
                        v = float(str(val).replace('%',''))
                    except:
                        return ""
                    color = "green" if v > 0 else ("red" if v < 0 else "black")
                    return f"color: {color}"
                styled_df = opt_df.style.map(color_profit_loss, subset=highlight_cols)
                st.dataframe(styled_df, use_container_width=True, hide_index=True)
            else:
                st.dataframe(opt_df, use_container_width=True, hide_index=True)
        else:
            st.info("No option trades found for summary.")
    st.markdown("---")

    with st.spinner("Loading tax summary..."):
        st.subheader("💵 Tax Summary by Year")
        summary_df = tax_summary()
        if not summary_df.empty:
            highlight_cols = [col for col in summary_df.columns if col.lower() in ["total gain/loss","total estimated tax"]]
            if highlight_cols:
                def color_profit_loss(val):
                    try:
                        v = float(str(val).replace('%',''))
                    except:
                        return ""
                    color = "green" if v > 0 else ("red" if v < 0 else "black")
                    return f"color: {color}"
                styled_df = summary_df.style.map(color_profit_loss, subset=highlight_cols)
                st.dataframe(styled_df, use_container_width=True, hide_index=True)
            else:
                st.dataframe(summary_df, use_container_width=True, hide_index=True)
        else:
            st.info("No closed trades found for tax summary.")
