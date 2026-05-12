import streamlit as st
import pandas as pd
import datetime
import altair as alt
from db.db_utils import load_closed_positions, load_option_trades
from ui.utils import color_profit_loss

LONG_TERM_TAX_RATE = 0.15
SHORT_TERM_TAX_RATE = 0.24
LONG_TERM_DAYS = 365

def _parse_date(dt):
    """Parse a date from string, date, or datetime."""
    if isinstance(dt, str):
        try:
            return datetime.datetime.fromisoformat(dt)
        except Exception:
            return None
    elif isinstance(dt, datetime.date):
        return datetime.datetime.combine(dt, datetime.time())
    elif isinstance(dt, datetime.datetime):
        return dt
    return None

@st.cache_data(ttl=300, show_spinner=False)
def aggregate_gains():
    """Aggregate gains for stocks and options, grouped by year and term."""
    closed_positions = load_closed_positions()
    # Include all closed statuses for options
    closed_options = []
    for status in ["expired", "exercised", "closed"]:
        closed_options += load_option_trades(status=status)
    yearly = {}
    yearly_breakdown = {}
    # Stocks
    for pos in closed_positions:
        entry_date = _parse_date(pos.get("entry_date"))
        exit_date = _parse_date(pos.get("exit_date"))
        entry_price = pos.get("entry_price", 0) or 0
        exit_price = pos.get("exit_price", 0) or 0
        quantity = pos.get("quantity", 0) or 0
        trade_type = pos.get("trade_type") or "Buy"
        if not exit_date or not entry_date:
            continue
        year = exit_date.year
        holding_period = (exit_date - entry_date).days
        if str(trade_type).lower() == "sell":
            gain = (entry_price - exit_price) * quantity
        else:
            gain = (exit_price - entry_price) * quantity
        term = "Long Term" if holding_period > LONG_TERM_DAYS else "Short Term"
        tax_rate = LONG_TERM_TAX_RATE if term == "Long Term" else SHORT_TERM_TAX_RATE
        yearly.setdefault(year, {"gain": 0, "tax": 0})
        yearly[year]["gain"] += gain
        yearly[year]["tax"] += gain * tax_rate
        yearly_breakdown.setdefault((year, "Stock", term), 0)
        yearly_breakdown[(year, "Stock", term)] += gain
    # Options
    for opt in closed_options:
        trade_date = _parse_date(opt.get("trade_date") or opt.get("entry_time"))
        close_date = _parse_date(opt.get("close_date") or opt.get("exit_time"))
        profit_loss = opt.get("profit_loss", 0) or 0
        try:
            profit_loss = float(profit_loss)
        except Exception:
            profit_loss = 0.0
        if not close_date or not trade_date:
            continue
        year = close_date.year
        holding_period = (close_date - trade_date).days
        term = "Long Term" if holding_period > LONG_TERM_DAYS else "Short Term"
        tax_rate = LONG_TERM_TAX_RATE if term == "Long Term" else SHORT_TERM_TAX_RATE
        yearly.setdefault(year, {"gain": 0, "tax": 0})
        yearly[year]["gain"] += profit_loss
        yearly[year]["tax"] += profit_loss * tax_rate
        yearly_breakdown.setdefault((year, "Options", term), 0)
        yearly_breakdown[(year, "Options", term)] += profit_loss
    return yearly, yearly_breakdown

def tax_summary():
    """Return a DataFrame summary of tax by year."""
    yearly, _ = aggregate_gains()
    if yearly:
        rows = []
        for year in sorted(yearly):
            rows.append({
                "Tax Year": year,
                "Total Gain/Loss": round(yearly[year]["gain"], 2),
                "Total Estimated Tax": round(yearly[year]["tax"], 2)
            })
        return pd.DataFrame(rows)
    else:
        return pd.DataFrame(columns=["Tax Year", "Total Gain/Loss", "Total Estimated Tax"])

def taxes_ui() -> None:
    """Streamlit UI for capital gains and losses by tax year."""
    st.title("Capital Gains & Losses by Tax Year")
    _, yearly_breakdown = aggregate_gains()
    summary_df = tax_summary()
    if not summary_df.empty:
        st.subheader("Tax Summary by Year")
        highlight_cols = [col for col in summary_df.columns if col.lower() in ["total estimated tax", "total gain/loss"]]
        if highlight_cols:
            styled_df = summary_df.style.map(color_profit_loss, subset=highlight_cols)
            st.dataframe(styled_df, width="stretch", hide_index=True)
        else:
            st.dataframe(summary_df, width="stretch", hide_index=True)

        # Only track total gain/loss in tax summary chart per year
        chart = alt.Chart(summary_df).mark_line(point=True).encode(
            x=alt.X('Tax Year:O', title='Tax Year'),
            y=alt.Y('Total Gain/Loss:Q', title='Total Gain/Loss'),
            color=alt.value('#4e79a7'),
            tooltip=['Tax Year', alt.Tooltip('Total Gain/Loss:Q', title='Total Gain/Loss')]
        )
        st.altair_chart(chart)
    else:
        st.info("No closed trades found for tax summary.")
    st.write("---")
    if yearly_breakdown:
        rows = []
        for breakdown_key in sorted(yearly_breakdown):
            year, asset, term = breakdown_key
            gain = yearly_breakdown[breakdown_key]
            tax_rate = 0.15 if term == "Long Term" else 0.24
            tax = gain * tax_rate
            rows.append({
                "Tax Year": year,
                "Asset Type": asset,
                "Term": term,
                "Gain/Loss": round(gain, 2),
                "Tax Rate": f"{int(tax_rate*100)}%",
                "Estimated Tax": round(tax, 2)
            })
        df = pd.DataFrame(rows)
        st.subheader("Summary by Tax Year, Asset, and Term")
        highlight_cols = [col for col in df.columns if col.lower() in ["estimated tax", "gain/loss"]]
        if highlight_cols:
            styled_df = df.style.map(color_profit_loss, subset=highlight_cols)
            st.dataframe(styled_df, width="stretch", hide_index=True)
        else:
            st.dataframe(df, width="stretch", hide_index=True)
    else:
        st.info("No closed trades found for capital gains calculation.")
