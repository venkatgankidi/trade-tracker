import streamlit as st
from ui.positions_ui import get_positions_summary
from ui.portfolio_report import get_position_summary_with_total, _get_portfolio_df
from ui.option_trades_ui import get_option_trades_summary
from ui.taxes_ui import tax_summary
import altair as alt
import pandas as pd
import yfinance as yf
from db.db_utils import PLATFORM_CACHE, load_option_trades, get_total_cash_by_platform, get_platform_cash_available_map
from ui.utils import get_platform_id_to_name_map, color_profit_loss, get_batch_option_prices, get_platform_option_exposure, get_options_cost_basis, get_options_portfolio_value
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
        platform_map = get_platform_id_to_name_map()
        opts_df = pd.DataFrame(open_opts)
        if "platform_id" in opts_df.columns:
            opts_df["Platform"] = opts_df["platform_id"].map(platform_map)
            
            # Add platform mapping for consolidated function
            open_opts_with_platform = opts_df.to_dict('records')
            platform_exposure = get_platform_option_exposure(open_opts_with_platform)
            
            # Add to rows
            for platform, exposure in platform_exposure.items():
                if exposure != 0:
                    rows.append({
                        "Platform": platform,
                        "Asset Type": "Options",
                        "Amount": float(exposure or 0.0)
                    })
    
    if not rows:
        return pd.DataFrame(columns=["Platform", "Asset Type", "Amount"])
    return pd.DataFrame(rows)

@st.cache_data(ttl=300, show_spinner=False)
def get_total_portfolio_value_by_platform() -> pd.DataFrame:
    """
    Calculate current portfolio value for all platforms (equities + options).
    Portfolio Value = equity current values + options current market values
    This represents the current market value of all positions.
    """
    portfolio_df = _get_portfolio_df()
    rows = []
    
    # Get portfolio value from positions (stocks and ETFs - current market value)
    equity_value_by_platform = {}
    if not portfolio_df.empty:
        equity_val = portfolio_df.groupby("platform", as_index=False)["current_value"].sum()
        for _, row in equity_val.iterrows():
            equity_value_by_platform[row["platform"]] = float(row["current_value"] or 0.0)
    
    # Get options portfolio value (current market value) for each platform
    options_value_by_platform = {}
    open_opts = load_option_trades(status="open")
    if open_opts:
        options_value_by_platform = get_options_portfolio_value(open_opts)
    
    # Combine equities and options for all platforms
    all_platforms = set(equity_value_by_platform.keys()) | set(options_value_by_platform.keys())
    for platform in all_platforms:
        equity_val = equity_value_by_platform.get(platform, 0.0)
        options_val = options_value_by_platform.get(platform, 0.0)
        total_val = equity_val + options_val
        if total_val > 0 or equity_val > 0:
            rows.append({
                "Platform": platform,
                "Portfolio Value": round(total_val, 2)
            })
    
    if not rows:
        return pd.DataFrame(columns=["Platform", "Portfolio Value"])
    
    result_df = pd.DataFrame(rows)
    return result_df.sort_values("Platform").reset_index(drop=True)

@st.cache_data(ttl=300, show_spinner=False)
def get_dashboard_position_summary() -> pd.DataFrame:
    """Returns a summary DataFrame for each platform (investment, value, unrealized gain).
    Includes both equities and options. This is dashboard-specific; portfolio_report shows equities only."""
    portfolio_df = _get_portfolio_df()
    rows = []
    for platform in PLATFORM_CACHE.keys():
        # Get equity investment (cost basis) from stocks and ETFs
        equity_group = portfolio_df[portfolio_df["platform"] == platform]
        equity_investment = equity_group["trade_cost"].sum() if not equity_group.empty else 0.0
        
        # Get equity portfolio value (current market value)
        equity_portfolio_value = equity_group["current_value"].sum() if not equity_group.empty else 0.0
        
        # Get options cost basis for this platform
        open_opts = load_option_trades(status="open")
        options_cost_basis = 0.0
        options_portfolio_value = 0.0
        if open_opts:
            platform_map = get_platform_id_to_name_map()
            platform_opts = [opt for opt in open_opts if platform_map.get(opt.get("platform_id")) == platform]
            if platform_opts:
                # Get cost basis (what you paid)
                options_cb_dict = get_options_cost_basis(platform_opts)
                options_cost_basis = abs(options_cb_dict.get(platform, 0.0))
                
                # Get portfolio value (current market value)
                options_pv_dict = get_options_portfolio_value(platform_opts)
                options_portfolio_value = options_pv_dict.get(platform, 0.0)
        
        # Total Investment = equities cost basis + options cost basis
        total_investment = equity_investment + options_cost_basis
        
        # Total Portfolio Value = equity current value + options current value
        total_portfolio_value = equity_portfolio_value + options_portfolio_value
        
        # Total Unrealized Gain = total portfolio value - total investment
        total_unrealized_gain = total_portfolio_value - total_investment
        
        if not equity_group.empty or total_investment > 0:
            percent_unrealized = (total_unrealized_gain / total_investment * 100) if total_investment else 0.0
            rows.append({
                "Platform": platform,
                "Total Investment": round(total_investment, 2),
                "Total Portfolio Value": round(total_portfolio_value, 2),
                "Total Unrealized Gains": round(total_unrealized_gain, 2),
                "Pct Unrealized Gain": f"{round(percent_unrealized, 2)}%"
            })
    return pd.DataFrame(rows)

@st.cache_data(ttl=300, show_spinner=False)
def get_dashboard_position_summary_with_total() -> pd.DataFrame:
    """Returns the dashboard position summary with an additional total row (includes equities + options)."""
    summary_df = get_dashboard_position_summary()
    if not summary_df.empty:
        total_investment = summary_df["Total Investment"].sum()
        total_value = summary_df["Total Portfolio Value"].sum()
        total_unrealized = summary_df["Total Unrealized Gains"].sum()
        percent_unrealized = (total_unrealized / total_investment * 100) if total_investment else 0.0
        overall_row = {
            "Platform": "Total",
            "Total Investment": round(total_investment, 2),
            "Total Portfolio Value": round(total_value, 2),
            "Total Unrealized Gains": round(total_unrealized, 2),
            "Pct Unrealized Gain": f"{round(percent_unrealized, 2)}%"
        }
        summary_df = pd.concat([summary_df, pd.DataFrame([overall_row])], ignore_index=True)
    return summary_df

@st.cache_data(ttl=300, show_spinner=False)
def get_total_investment_for_cashflow() -> pd.DataFrame:
    """
    Calculate total investment for cash flow tracking (includes both equities and options).
    Total Investment = equities (trade_cost) + options cost basis (option_open_price * 100)
    This represents what you paid for all positions.
    """
    portfolio_df = _get_portfolio_df()
    rows = []
    
    # Get investment from positions (stocks and ETFs - cost basis)
    equity_investment_by_platform = {}
    if not portfolio_df.empty:
        equity_inv = portfolio_df.groupby("platform", as_index=False)["trade_cost"].sum()
        for _, row in equity_inv.iterrows():
            equity_investment_by_platform[row["platform"]] = float(row["trade_cost"] or 0.0)
    
    # Get options cost basis (what you paid) for each platform
    options_cost_basis_by_platform = {}
    open_opts = load_option_trades(status="open")
    if open_opts:
        options_cost_basis_by_platform = get_options_cost_basis(open_opts)
    
    # Combine equities and options for all platforms
    all_platforms = set(equity_investment_by_platform.keys()) | set(options_cost_basis_by_platform.keys())
    for platform in all_platforms:
        equity_inv = equity_investment_by_platform.get(platform, 0.0)
        options_cb = abs(options_cost_basis_by_platform.get(platform, 0.0))
        total_inv = equity_inv + options_cb
        if total_inv > 0 or equity_inv > 0 or options_cb > 0:
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
        st.subheader("💵 Summary by Platform")
        deposits_by_platform = get_total_cash_by_platform()  # deposits - withdrawals
        platform_cash_map = get_platform_cash_available_map()  # explicit per-platform cash available (true account value)

        # Build list of all platforms from both sources, stable sort
        all_platforms = sorted(set(list(deposits_by_platform.keys()) + list(platform_cash_map.keys())))
        if all_platforms:
            cash_summary_data = []
            for platform in all_platforms:
                deposits = round(deposits_by_platform.get(platform, 0.0), 2)
                cash_available = round(platform_cash_map.get(platform, deposits), 2)  # fallback to deposits if missing
                cash_summary_data.append({
                    "Platform": platform,
                    "Deposits & Withdrawals": deposits,
                    "Cash Available": cash_available
                })

            cash_summary_df = pd.DataFrame(cash_summary_data)

            # Attach Total Investment and Portfolio Value like before
            investment_df = get_total_investment_for_cashflow()
            investment_map = dict(zip(investment_df["Platform"], investment_df["Total Investment"])) if not investment_df.empty else {}
            cash_summary_df["Total Investment"] = cash_summary_df["Platform"].map(lambda p: investment_map.get(p, 0.0))

            portfolio_value_df = get_total_portfolio_value_by_platform()
            portfolio_value_map = dict(zip(portfolio_value_df["Platform"], portfolio_value_df["Portfolio Value"])) if not portfolio_value_df.empty else {}
            cash_summary_df["Portfolio Value"] = cash_summary_df["Platform"].map(lambda p: portfolio_value_map.get(p, 0.0))

            # Total Account Value = Cash Available + Portfolio Value (true account value)
            cash_summary_df["Total Account Value"] = (cash_summary_df["Cash Available"] + cash_summary_df["Portfolio Value"]).round(2)

            # Ensure Total Account Value is last column for display
            display_cols = ["Platform", "Deposits & Withdrawals", "Cash Available", "Total Investment", "Portfolio Value", "Total Account Value"]
            st.dataframe(cash_summary_df[display_cols], width="stretch", hide_index=True)
        else:
            st.info("No platform cash or cash flows recorded.")
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
        summary_df = get_dashboard_position_summary_with_total()
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
            highlight_cols = [col for col in opt_df.columns if col.lower() in ["profit_loss", "gain", "total option p/l (closed)", "unrealized gains (open)"]]
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
