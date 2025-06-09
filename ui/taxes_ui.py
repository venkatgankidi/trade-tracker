import streamlit as st
import datetime
from db.db_utils import load_closed_positions, load_option_trades

def taxes_ui():
    import pandas as pd
    st.title("Capital Gains & Losses by Tax Year")

    # Tax rates (can be adjusted)
    LONG_TERM_TAX_RATE = 0.15
    SHORT_TERM_TAX_RATE = 0.24

    # Load closed positions and option trades
    closed_positions = load_closed_positions()
    closed_options = load_option_trades(status="closed")  # Adjust status if needed

    # Helper to parse date
    def parse_date(dt):
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

    # Aggregate by year, asset type, and term
    yearly = {}

    # Process closed positions (Stocks)
    for pos in closed_positions:
        entry_time = parse_date(pos.get("entry_time"))
        exit_time = parse_date(pos.get("exit_time"))
        entry_price = pos.get("entry_price", 0) or 0
        exit_price = pos.get("exit_price", 0) or 0
        quantity = pos.get("quantity", 0) or 0
        trade_type = pos.get("trade_type", "Buy")
        if not exit_time or not entry_time:
            continue
        year = exit_time.year
        holding_period = (exit_time - entry_time).days
        if trade_type.lower() == "sell":
            gain = (entry_price - exit_price) * quantity
        else:
            gain = (exit_price - entry_price) * quantity
        term = "Long Term" if holding_period > 365 else "Short Term"
        asset = "Stock"
        yearly.setdefault((year, asset, term), 0)
        yearly[(year, asset, term)] += gain

    # Process closed option trades (Options)
    for opt in closed_options:
        trade_date = parse_date(opt.get("trade_date") or opt.get("entry_time"))
        close_date = parse_date(opt.get("close_date") or opt.get("exit_time"))
        profit_loss = opt.get("profit_loss", 0) or 0
        if not close_date or not trade_date:
            continue
        year = close_date.year
        holding_period = (close_date - trade_date).days
        term = "Long Term" if holding_period > 365 else "Short Term"
        asset = "Option"
        yearly.setdefault((year, asset, term), 0)
        yearly[(year, asset, term)] += profit_loss

    # Prepare DataFrame for display
    if yearly:
        rows = []
        for (year, asset, term) in sorted(yearly):
            gain = yearly[(year, asset, term)]
            tax_rate = LONG_TERM_TAX_RATE if term == "Long Term" else SHORT_TERM_TAX_RATE
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
        st.dataframe(df, use_container_width=True)
    else:
        st.info("No closed trades found for capital gains calculation.")
