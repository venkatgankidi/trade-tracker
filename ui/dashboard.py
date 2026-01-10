import streamlit as st
from ui.positions_ui import get_positions_summary
from ui.portfolio_report import get_position_summary_with_total, _get_portfolio_df
from ui.option_trades_ui import get_option_trades_summary
from ui.taxes_ui import tax_summary
import altair as alt
import pandas as pd
import yfinance as yf
from db.db_utils import PLATFORM_CACHE, load_option_trades, get_total_cash_by_platform
from ui.utils import get_platform_id_to_name_map, color_profit_loss
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
        platform_map = get_platform_id_to_name_map()
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

@st.cache_data(ttl=300, show_spinner=False)
def get_total_investment_by_platform() -> pd.DataFrame:
    """
    Calculate total investment in cash by platform (equities only, for portfolio summary).
    Total Investment = equities (trade_cost) from stocks and ETFs only
    (Options excluded as we are not pulling realtime options data)
    """
    portfolio_df = _get_portfolio_df()
    rows = []
    
    # Get investment from positions (stocks and ETFs only)
    if not portfolio_df.empty:
        platform_investment = portfolio_df.groupby("platform", as_index=False)["trade_cost"].sum()
        for _, row in platform_investment.iterrows():
            rows.append({
                "Platform": row["platform"],
                "Total Investment": round(float(row["trade_cost"] or 0.0), 2)
            })
    
    if not rows:
        return pd.DataFrame(columns=["Platform", "Total Investment"])
    
    result_df = pd.DataFrame(rows)
    result_df["Total Investment"] = result_df["Total Investment"].round(2)
    return result_df.sort_values("Platform").reset_index(drop=True)

@st.cache_data(ttl=300, show_spinner=False)
def get_total_investment_for_cashflow() -> pd.DataFrame:
    """
    Calculate total investment for cash flow tracking (includes both equities and options).
    Total Investment = equities (trade_cost) + options exposure (excluding cash)
    This is used for cash flow analysis to reflect total capital deployed.
    """
    portfolio_df = _get_portfolio_df()
    rows = []
    
    # Get investment from positions (stocks and ETFs)
    equity_investment_by_platform = {}
    if not portfolio_df.empty:
        equity_inv = portfolio_df.groupby("platform", as_index=False)["trade_cost"].sum()
        for _, row in equity_inv.iterrows():
            equity_investment_by_platform[row["platform"]] = float(row["trade_cost"] or 0.0)
    
    # Get options exposure for each platform
    options_exposure_by_platform = {}
    open_opts = load_option_trades(status="open")
    if open_opts:
        platform_map = get_platform_id_to_name_map()
        opts_df = pd.DataFrame(open_opts)
        if "platform_id" in opts_df.columns:
            opts_df["Platform"] = opts_df["platform_id"].map(platform_map)
            opts_df["option_open_price"] = pd.to_numeric(opts_df.get("option_open_price", 0), errors="coerce").fillna(0)
            opts_df["transaction_type"] = opts_df["transaction_type"].str.lower()
            opts_df["Option Exposure"] = opts_df.apply(
                lambda x: float(x["option_open_price"]) * 100.0 * (1 if x["transaction_type"] == "debit" else -1), 
                axis=1
            )
            opts_inv = opts_df.groupby("Platform", as_index=False)["Option Exposure"].sum()
            for _, row in opts_inv.iterrows():
                options_exposure_by_platform[row["Platform"]] = float(row["Option Exposure"] or 0.0)
    
    # Combine equities and options for all platforms
    all_platforms = set(equity_investment_by_platform.keys()) | set(options_exposure_by_platform.keys())
    for platform in all_platforms:
        equity_inv = equity_investment_by_platform.get(platform, 0.0)
        options_exp = abs(options_exposure_by_platform.get(platform, 0.0))
        total_inv = equity_inv + options_exp
        if total_inv > 0 or equity_inv > 0 or options_exp > 0:
            rows.append({
                "Platform": platform,
                "Total Investment": round(total_inv, 2)
            })
    
    if not rows:
        return pd.DataFrame(columns=["Platform", "Total Investment"])
    
    result_df = pd.DataFrame(rows)
    return result_df.sort_values("Platform").reset_index(drop=True)

def dashboard():
    st.header("📊 Dashboard")

    # --- Cash Summary by Platform with Total Investment and ROI ---
    with st.spinner("Loading cash summary..."):
        st.subheader("💵 Cash & Investment by Platform")
        cash_by_platform = get_total_cash_by_platform()
        
        if cash_by_platform:
            # Create summary table
            cash_summary_data = []
            for platform, cash in sorted(cash_by_platform.items()):
                cash_summary_data.append({
                    "Platform": platform,
                    "Total Cash": round(cash, 2)
                })
            
            cash_summary_df = pd.DataFrame(cash_summary_data)
            
            # Get portfolio value and investment per platform
            portfolio_df = _get_portfolio_df()
            platform_values = {}
            if not portfolio_df.empty:
                for platform in portfolio_df["platform"].unique():
                    platform_values[platform] = portfolio_df[portfolio_df["platform"] == platform]["current_value"].sum()
            
            # Add total investment (including both equities and options for cash flow tracking)
            investment_df = get_total_investment_for_cashflow()
            investment_map = {}
            if not investment_df.empty:
                investment_map = dict(zip(investment_df["Platform"], investment_df["Total Investment"]))
            
            cash_summary_df["Total Investment"] = cash_summary_df["Platform"].map(
                lambda p: investment_map.get(p, 0.0)
            )
            
            # Add portfolio value and ROI
            cash_summary_df["Portfolio Value"] = cash_summary_df["Platform"].map(
                lambda p: round(platform_values.get(p, 0), 2) if p in platform_values else 0
            )
            cash_summary_df["ROI %"] = cash_summary_df.apply(
                lambda row: round((row["Portfolio Value"] / row["Total Investment"] - 1) * 100, 2) if row["Total Investment"] > 0 else 0,
                axis=1
            )
            
            # Format and display
            highlight_cols = [col for col in cash_summary_df.columns if col.lower() in ["roi %"]]
            if highlight_cols:
                def color_roi(val):
                    try:
                        v = float(val)
                    except:
                        return ""
                    color = "green" if v > 0 else ("red" if v < 0 else "black")
                    return f"color: {color}"
                styled_df = cash_summary_df.style.map(color_roi, subset=highlight_cols)
                st.dataframe(styled_df, width="stretch", hide_index=True)
            else:
                st.dataframe(cash_summary_df, width="stretch", hide_index=True)
        else:
            st.info("No cash flows recorded.")
    st.markdown("---")

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
            st.dataframe(pivot[amount_cols].round(2), width="stretch", hide_index=True)
            
            # Display percentages table
            st.write("Asset Distribution Percentages (%)")
            st.dataframe(pivot[pct_cols].round(2), width="stretch", hide_index=True)
            
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
                                theta=alt.Theta(field="Amount", type="quantitative"),
                                color=alt.Color(field="Asset Type", type="nominal"),
                                tooltip=[
                                    alt.Tooltip("Asset Type:N"),
                                    alt.Tooltip("Amount:Q", format="$,.2f"),
                                    alt.Tooltip("Percentage:Q", format=".1f", title="Percentage (%)")
                                ]
                            ).properties(
                                title=f"{platform}"
                            )
                            
                            # Add percentage labels
                            pie_labels = alt.Chart(pie_df).mark_text(radius=80, size=11).encode(
                                theta=alt.Theta(field="Amount", type="quantitative", stack=True),
                                text=alt.Text("Percentage:Q", format=".1f", title="Percentage (%)"),
                                color=alt.value("white")
                            )
                            
                            st.altair_chart(pie_chart + pie_labels)
        else:
            st.info("No portfolio or option data available to compute allocation.")

    with st.spinner("Loading positions summary..."):
        st.subheader("📈 Positions Summary")
        pos_mgr_df = get_positions_summary()
        if not pos_mgr_df.empty:
            highlight_cols = [col for col in pos_mgr_df.columns if col.lower() in ["profit_loss", "gain", "total p/l (closed)", "pct_unrealized_gain"]]
            if highlight_cols:
                styled_df = pos_mgr_df.style.map(color_profit_loss, subset=highlight_cols)
                st.dataframe(styled_df, width="stretch", hide_index=True)
            else:
                st.dataframe(pos_mgr_df, width="stretch", hide_index=True)
        else:
            st.info("No positions found for summary.")
    st.markdown("---")

    with st.spinner("Loading portfolio summary..."):
        st.subheader("💼 Portfolio Summary")
        summary_df = get_position_summary_with_total()
        if not summary_df.empty:
            highlight_cols = [col for col in summary_df.columns if col.lower() in ["total unrealized gains", "pct unrealized gain"]]
            if highlight_cols:
                styled_df = summary_df.style.map(color_profit_loss, subset=highlight_cols)
                st.dataframe(styled_df, width="stretch", hide_index=True)
            else:
                st.dataframe(summary_df, width="stretch", hide_index=True)
        else:
            st.info("No positions found for summary.")
    st.markdown("---")

    with st.spinner("Loading option trades summary..."):
        st.subheader("📝 Option Trades Summary")
        opt_df = get_option_trades_summary()
        if not opt_df.empty:
            highlight_cols = [col for col in opt_df.columns if col.lower() in ["profit_loss", "gain", "total option p/l (closed)"]]
            if highlight_cols:
                styled_df = opt_df.style.map(color_profit_loss, subset=highlight_cols)
                st.dataframe(styled_df, width="stretch", hide_index=True)
            else:
                st.dataframe(opt_df, width="stretch", hide_index=True)
        else:
            st.info("No option trades found for summary.")
    st.markdown("---")

    with st.spinner("Loading tax summary..."):
        st.subheader("💵 Tax Summary by Year")
        summary_df = tax_summary()
        if not summary_df.empty:
            highlight_cols = [col for col in summary_df.columns if col.lower() in ["total gain/loss","total estimated tax"]]
            if highlight_cols:
                styled_df = summary_df.style.map(color_profit_loss, subset=highlight_cols)
                st.dataframe(styled_df, width="stretch", hide_index=True)
            else:
                st.dataframe(summary_df, width="stretch", hide_index=True)
        else:
            st.info("No closed trades found for tax summary.")
