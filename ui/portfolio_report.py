import streamlit as st
import pandas as pd
import yfinance as yf
from db.db_utils import PLATFORM_CACHE, load_positions, load_option_trades
from typing import Optional, List, Dict
import altair as alt
from ui.utils import color_profit_loss, get_platform_id_to_name_map, get_platform_option_exposure

@st.cache_data(ttl=300, show_spinner=False)
def _get_ticker_prices(tickers: List[str]) -> Dict[str, Optional[float]]:
    """Fetch current prices for a list of tickers using yfinance. Cached for 5 minutes."""
    price_map = {}
    for ticker in tickers:
        try:
            price = yf.Ticker(ticker).history(period="1d", interval="1m")["Close"].iloc[-1]
            price_map[ticker] = price
        except Exception:
            price_map[ticker] = None
    return price_map

def _get_portfolio_df() -> pd.DataFrame:
    """Returns a DataFrame with portfolio holdings, including current price and unrealized gain/loss."""
    open_positions = load_positions()
    if not open_positions:
        return pd.DataFrame(columns=["platform", "ticker", "total_quantity", "average_price", "trade_cost", "current_price", "current_value", "unrealized_gain", "percent_profit_loss"])
    df = pd.DataFrame(open_positions)
    platform_map = get_platform_id_to_name_map()
    df["platform"] = df["platform_id"].map(platform_map)
    summary = (
        df.groupby(["platform", "ticker"])
        .apply(lambda g: pd.Series({
            "total_quantity": g["quantity"].sum(),
            "average_price": (g["entry_price"] * g["quantity"]).sum() / g["quantity"].sum() if g["quantity"].sum() else 0,
            "trade_cost": (g["entry_price"] * g["quantity"]).sum()
        }), include_groups=False)
        .reset_index()
    )
    unique_tickers = summary["ticker"].unique().tolist()
    ticker_price_map = _get_ticker_prices(unique_tickers)
    summary["current_price"] = summary["ticker"].map(ticker_price_map)
    summary["current_value"] = summary["current_price"] * summary["total_quantity"]
    summary["unrealized_gain"] = summary["current_value"] - summary["trade_cost"]
    summary["percent_profit_loss"] = (summary["unrealized_gain"] / summary["trade_cost"]) * 100
    return summary

def get_position_summary() -> pd.DataFrame:
    """Returns a summary DataFrame for each platform (investment, value, unrealized gain).
    Total Investment includes both equities and options with real-time prices."""
    portfolio_df = _get_portfolio_df()
    rows = []
    for platform in PLATFORM_CACHE.keys():
        # Get equity investment from stocks and ETFs
        equity_group = portfolio_df[portfolio_df["platform"] == platform]
        equity_investment = equity_group["trade_cost"].sum() if not equity_group.empty else 0.0
        
        # Get options exposure for this platform
        open_opts = load_option_trades(status="open")
        options_exposure = 0.0
        if open_opts:
            opts_df = pd.DataFrame(open_opts)
            platform_map = get_platform_id_to_name_map()
            opts_df["Platform"] = opts_df["platform_id"].map(platform_map)
            platform_opts = [opt for opt in open_opts if platform_map.get(opt.get("platform_id")) == platform]
            if platform_opts:
                # Use consolidated function to calculate option exposure
                platform_exposure_dict = get_platform_option_exposure(platform_opts)
                options_exposure = platform_exposure_dict.get(platform, 0.0)
        
        # Total Investment = equities + absolute value of options exposure
        total_investment = equity_investment + abs(options_exposure)
        
        if not equity_group.empty or total_investment > 0:
            total_portfolio_value = equity_group["current_value"].sum() if not equity_group.empty else 0.0
            total_unrealized_gain = equity_group["unrealized_gain"].sum() if not equity_group.empty else 0.0
            percent_unrealized = (total_unrealized_gain / total_investment * 100) if total_investment else 0.0
            rows.append({
                "Platform": platform,
                "Total Investment": round(total_investment, 2),
                "Total Portfolio Value": round(total_portfolio_value, 2),
                "Total Unrealized Gains": round(total_unrealized_gain, 2),
                "Pct Unrealized Gain": f"{round(percent_unrealized, 2)}%"
            })
    return pd.DataFrame(rows)

def get_position_summary_with_total() -> pd.DataFrame:
    """Returns the position summary with an additional total row."""
    summary_df = get_position_summary()
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

def portfolio_ui() -> None:
    """Streamlit UI for portfolio summary and holdings, with formatted output and error handling."""
    st.title("💼 Portfolio")
    with st.spinner("Loading portfolio summary..."):
        st.subheader("📊 Portfolio Summary")
        summary_df = get_position_summary_with_total()
        if not summary_df.empty:
            highlight_cols = [col for col in summary_df.columns if col.lower() in ["total unrealized gains", "pct unrealized gain"]]
            if highlight_cols:
                styled_df = summary_df.style.map(color_profit_loss, subset=highlight_cols)
                st.dataframe(styled_df, width="stretch", hide_index=True)
            else:
                st.dataframe(summary_df, width="stretch", hide_index=True)
            # Restore line chart: Portfolio Value and Unrealized Gains by Platform
            if 'Platform' in summary_df.columns and 'Total Portfolio Value' in summary_df.columns and 'Total Unrealized Gains' in summary_df.columns:
                plot_df = summary_df[summary_df['Platform'] != 'Total'].copy()
                melted = plot_df.melt(id_vars=['Platform'], value_vars=['Total Portfolio Value', 'Total Unrealized Gains'], var_name='Metric', value_name='Value')
                chart = alt.Chart(melted).mark_line(point=True).encode(
                    x=alt.X('Platform:N', title='Platform', axis=alt.Axis(labelAngle=-45)),
                    y=alt.Y('Value:Q'),
                    color=alt.Color('Metric:N', title='Metric'),
                    tooltip=['Platform', 'Metric', 'Value']
                )
                st.altair_chart(chart)
        else:
            st.info("No positions found for summary.")
    st.markdown("---")
    with st.spinner("Loading portfolio holdings..."):
        st.subheader("📦 Portfolio Holdings")
        portfolio_df = _get_portfolio_df()
        if not portfolio_df.empty:
            for platform, group_df in portfolio_df.groupby("platform"):
                st.write(f"**Platform:** {platform}")
                display_df = group_df.copy()
                display_df = display_df.sort_values("ticker")
                display_df = display_df.drop(columns=["platform"], errors='ignore')
                if "percent_profit_loss" in display_df.columns:
                    display_df["percent_profit_loss"] = display_df["percent_profit_loss"].apply(lambda x: f"{x:.2f}%" if pd.notna(x) else "")
                highlight_cols = [col for col in display_df.columns if col.lower() in [ "percent_profit_loss", "unrealized_gain"]]
                if highlight_cols:
                    styled_df = display_df.style.map(color_profit_loss, subset=highlight_cols)
                    st.dataframe(styled_df, width="stretch", hide_index=True)
                else:
                    st.dataframe(display_df, width="stretch", hide_index=True)
                # Change portfolio holdings chart to plot trade cost, current value, and profit/loss per ticker in a line graph
                if 'ticker' in display_df.columns and 'trade_cost' in display_df.columns and 'current_value' in display_df.columns and 'unrealized_gain' in display_df.columns:
                    melted = display_df.melt(id_vars=['ticker'], value_vars=['trade_cost', 'current_value', 'unrealized_gain'], var_name='Metric', value_name='Value')
                    chart = alt.Chart(melted).mark_line(point=True).encode(
                        x=alt.X('ticker:N', title='Ticker'),
                        y=alt.Y('Value:Q', title='Amount'),
                        color=alt.Color('Metric:N', title='Metric'),
                        tooltip=['ticker', 'Metric', 'Value']
                    )
                    st.altair_chart(chart)
        else:
            st.info("No portfolio holdings found.")
