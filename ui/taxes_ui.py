import streamlit as st
import pandas as pd
import datetime
from datetime import timedelta
import altair as alt
from collections import defaultdict
from db.db_utils import load_closed_positions, load_option_trades, load_all_trades
from ui.utils import color_profit_loss

LONG_TERM_TAX_RATE = 0.15
SHORT_TERM_TAX_RATE = 0.24
LONG_TERM_DAYS = 365
WASH_SALE_WINDOW_DAYS = 30


def _parse_date(dt):
    """Parse a date from string, date, or datetime into datetime."""
    if isinstance(dt, str):
        try:
            return datetime.datetime.fromisoformat(dt)
        except Exception:
            return None
    elif isinstance(dt, datetime.datetime):
        return dt
    elif isinstance(dt, datetime.date):
        return datetime.datetime.combine(dt, datetime.time())
    return None


# ---------------------------------------------------------------------------
# Wash-sale detection engine
# ---------------------------------------------------------------------------

def detect_wash_sales(closed_positions, closed_options, all_raw_trades, all_option_trades):
    """Detect IRS §1091 wash sales across stock positions and options.

    A capital loss is disallowed when a *substantially identical* security is
    purchased within 30 days **before or after** the sale that generated the
    loss.

    Coverage:
    ┌─────────────────────────────────┬────────────────────────────────────────┐
    │ Loss source                     │ Triggers wash sale if…                 │
    ├─────────────────────────────────┼────────────────────────────────────────┤
    │ Stock position closed at loss   │ Stock buy of same ticker in window     │
    │ Stock position closed at loss   │ Any option on same ticker opened       │
    │ Option trade closed at loss     │ Stock buy of same ticker in window     │
    │ Option trade closed at loss     │ Another option on same ticker opened   │
    └─────────────────────────────────┴────────────────────────────────────────┘

    Returns:
        list[dict] — one record per disallowed loss transaction, containing:
          ticker, asset_type, sale_date, raw_loss, disallowed_loss,
          replacement_type, replacement_date, replacement_quantity,
          basis_adj_per_share, year, term, tax_rate
    """
    window = timedelta(days=WASH_SALE_WINDOW_DAYS)

    # --- Index stock buys by ticker ----------------------------------------
    stock_buys_by_ticker: dict = defaultdict(list)
    for t in all_raw_trades:
        if str(t.get("trade_type", "")).lower() == "buy":
            d = _parse_date(t.get("date"))
            if d:
                stock_buys_by_ticker[t["ticker"]].append({
                    "date": d,
                    "price": float(t.get("price") or 0),
                    "quantity": float(t.get("quantity") or 0),
                })

    # --- Index option openings by ticker ------------------------------------
    option_opens_by_ticker: dict = defaultdict(list)
    for opt in all_option_trades:
        d = _parse_date(opt.get("trade_date"))
        if d:
            option_opens_by_ticker[opt["ticker"]].append({
                "id": opt.get("id"),
                "date": d,
                "strategy": opt.get("strategy", ""),
                "quantity": int(opt.get("quantity") or 1),
                "option_open_price": float(opt.get("option_open_price") or 0),
            })

    def _find_stock_replacement(ticker, loss_date):
        """Return earliest stock buy of same ticker within the wash-sale window.

        Only stock-to-stock matches are considered per the simplified scope.
        Same-calendar-day buys are excluded (settlement-day matching).
        """
        start = loss_date - window
        end = loss_date + window
        loss_day = loss_date.date()
        for b in sorted(stock_buys_by_ticker.get(ticker, []), key=lambda x: x["date"]):
            if start <= b["date"] <= end and b["date"].date() != loss_day:
                return {
                    "type": "Stock Buy",
                    "date": b["date"],
                    "ticker": ticker,
                    "price": b["price"],
                    "quantity": b["quantity"],
                }
        return None

    def _find_option_replacement(ticker, loss_date, exclude_opt_id=None):
        """Return earliest option open of same ticker within the wash-sale window.

        Only option-to-option matches are considered per the simplified scope.
        The originating trade (exclude_opt_id) is never counted as its own replacement.
        Same-calendar-day opens are excluded.
        """
        start = loss_date - window
        end = loss_date + window
        loss_day = loss_date.date()
        for o in sorted(option_opens_by_ticker.get(ticker, []), key=lambda x: x["date"]):
            if o.get("id") == exclude_opt_id:
                continue
            if start <= o["date"] <= end and o["date"].date() != loss_day:
                return {
                    "type": f"Option Open ({o['strategy'].title()})",
                    "date": o["date"],
                    "ticker": ticker,
                    "price": o["option_open_price"],
                    "quantity": o["quantity"] * 100,  # contracts → shares
                }
        return None

    wash_sales = []

    # --- Stock position losses ----------------------------------------------
    for pos in closed_positions:
        try:
            pl = float(pos.get("profit_loss") or 0)
        except Exception:
            pl = 0.0
        if pl >= 0:
            continue

        ticker = pos.get("ticker")
        exit_date = _parse_date(pos.get("exit_date"))
        entry_date = _parse_date(pos.get("entry_date"))
        if not exit_date or not ticker:
            continue

        # Stock losses: only check for a replacement stock buy
        replacement = _find_stock_replacement(ticker, exit_date)
        if not replacement:
            continue

        disallowed = abs(pl)
        holding_period = (exit_date - entry_date).days if entry_date else 0
        term = "Long Term" if holding_period > LONG_TERM_DAYS else "Short Term"
        tax_rate = LONG_TERM_TAX_RATE if term == "Long Term" else SHORT_TERM_TAX_RATE

        # Per-share cost-basis uplift for stock replacement lots
        repl_qty = replacement["quantity"]
        basis_adj_per_share = round(disallowed / repl_qty, 4) if repl_qty > 0 else None

        wash_sales.append({
            "ticker": ticker,
            "asset_type": "Stock",
            "sale_date": exit_date,
            "raw_loss": pl,
            "disallowed_loss": disallowed,
            "replacement_type": replacement["type"],
            "replacement_date": replacement["date"],
            "replacement_quantity": repl_qty,
            "basis_adj_per_share": basis_adj_per_share,
            "year": exit_date.year,
            "term": term,
            "tax_rate": tax_rate,
        })

    # --- Option losses ------------------------------------------------------
    for opt in closed_options:
        try:
            pl = float(opt.get("profit_loss") or 0)
        except Exception:
            pl = 0.0
        if pl >= 0:
            continue

        ticker = opt.get("ticker")
        close_date = _parse_date(opt.get("close_date"))
        trade_date = _parse_date(opt.get("trade_date"))
        if not close_date or not ticker:
            continue

        # Option losses: only check for a replacement option open
        replacement = _find_option_replacement(ticker, close_date, exclude_opt_id=opt.get("id"))
        if not replacement:
            continue

        disallowed = abs(pl)
        holding_period = (close_date - trade_date).days if trade_date else 0
        term = "Long Term" if holding_period > LONG_TERM_DAYS else "Short Term"
        tax_rate = LONG_TERM_TAX_RATE if term == "Long Term" else SHORT_TERM_TAX_RATE

        repl_qty = replacement["quantity"]
        # Option replacements carry the deferred loss at the contract level (no per-share figure)
        basis_adj_per_share = None

        wash_sales.append({
            "ticker": ticker,
            "asset_type": "Option",
            "sale_date": close_date,
            "raw_loss": pl,
            "disallowed_loss": disallowed,
            "replacement_type": replacement["type"],
            "replacement_date": replacement["date"],
            "replacement_quantity": repl_qty,
            "basis_adj_per_share": basis_adj_per_share,
            "year": close_date.year,
            "term": term,
            "tax_rate": tax_rate,
        })

    return wash_sales


# ---------------------------------------------------------------------------
# Aggregation (with wash-sale adjustments)
# ---------------------------------------------------------------------------

@st.cache_data(ttl=300, show_spinner=False)
def aggregate_gains():
    """Aggregate gains for stocks and options, grouped by year and term.

    Returns:
        yearly (dict)          — {year: {gain, tax, wash_sale_disallowed}}
        yearly_breakdown (dict)— {(year, asset, term): gain}
        wash_sales (list)      — raw wash-sale records from detect_wash_sales()
    """
    closed_positions = load_closed_positions()
    closed_options = []
    for status in ["expired", "exercised", "closed"]:
        closed_options += load_option_trades(status=status)

    # Full trade history needed for wash-sale detection
    all_raw_trades = load_all_trades()
    all_option_trades = load_option_trades()  # all statuses

    yearly = {}
    yearly_breakdown = {}

    # --- Stocks ---
    for pos in closed_positions:
        entry_date = _parse_date(pos.get("entry_date"))
        exit_date = _parse_date(pos.get("exit_date"))
        entry_price = pos.get("entry_price", 0) or 0
        exit_price = pos.get("exit_price", 0) or 0
        quantity = pos.get("quantity", 0) or 0
        direction = pos.get("direction") or "Long"
        if not exit_date or not entry_date:
            continue
        year = exit_date.year
        holding_period = (exit_date - entry_date).days
        raw_pl = pos.get("profit_loss")
        if raw_pl is not None:
            try:
                gain = float(raw_pl)
            except Exception:
                gain = 0.0
        else:
            if str(direction).capitalize() == "Short":
                gain = (entry_price - exit_price) * quantity
            else:
                gain = (exit_price - entry_price) * quantity
        term = "Long Term" if holding_period > LONG_TERM_DAYS else "Short Term"
        tax_rate = LONG_TERM_TAX_RATE if term == "Long Term" else SHORT_TERM_TAX_RATE
        yearly.setdefault(year, {"gain": 0.0, "tax": 0.0, "wash_sale_disallowed": 0.0})
        yearly[year]["gain"] += gain
        yearly[year]["tax"] += gain * tax_rate
        yearly_breakdown.setdefault((year, "Stock", term), 0.0)
        yearly_breakdown[(year, "Stock", term)] += gain

    # --- Options ---
    for opt in closed_options:
        trade_date = _parse_date(opt.get("trade_date") or opt.get("entry_time"))
        close_date = _parse_date(opt.get("close_date") or opt.get("exit_time"))
        try:
            profit_loss = float(opt.get("profit_loss") or 0)
        except Exception:
            profit_loss = 0.0
        if not close_date or not trade_date:
            continue
        year = close_date.year
        holding_period = (close_date - trade_date).days
        term = "Long Term" if holding_period > LONG_TERM_DAYS else "Short Term"
        tax_rate = LONG_TERM_TAX_RATE if term == "Long Term" else SHORT_TERM_TAX_RATE
        yearly.setdefault(year, {"gain": 0.0, "tax": 0.0, "wash_sale_disallowed": 0.0})
        yearly[year]["gain"] += profit_loss
        yearly[year]["tax"] += profit_loss * tax_rate
        yearly_breakdown.setdefault((year, "Options", term), 0.0)
        yearly_breakdown[(year, "Options", term)] += profit_loss

    # Ensure all yearly entries have the wash_sale_disallowed key
    for year in yearly:
        yearly[year].setdefault("wash_sale_disallowed", 0.0)

    # --- Wash-sale detection & adjustment ---
    wash_sales = detect_wash_sales(
        closed_positions, closed_options, all_raw_trades, all_option_trades
    )

    for ws in wash_sales:
        year = ws["year"]
        disallowed = ws["disallowed_loss"]
        tax_rate = ws["tax_rate"]
        yearly.setdefault(year, {"gain": 0.0, "tax": 0.0, "wash_sale_disallowed": 0.0})
        # The loss was already counted (negative gain). Adding it back disallows it.
        yearly[year]["gain"] += disallowed
        yearly[year]["tax"] += disallowed * tax_rate
        yearly[year]["wash_sale_disallowed"] += disallowed

    return yearly, yearly_breakdown, wash_sales


# ---------------------------------------------------------------------------
# Summary helpers
# ---------------------------------------------------------------------------

def tax_summary():
    """Return a DataFrame summary of tax by year, including wash-sale columns."""
    yearly, _, _ = aggregate_gains()
    if not yearly:
        return pd.DataFrame(columns=[
            "Tax Year", "Raw Gain/Loss", "Wash Sale Disallowed",
            "Adjusted Gain/Loss", "Total Estimated Tax"
        ])
    rows = []
    for year in sorted(yearly):
        data = yearly[year]
        raw_gain = data["gain"] - data["wash_sale_disallowed"]  # before adjustment
        adjusted_gain = data["gain"]  # after wash-sale add-back
        rows.append({
            "Tax Year": year,
            "Raw Gain/Loss": round(raw_gain, 2),
            "Wash Sale Disallowed": round(data["wash_sale_disallowed"], 2),
            "Adjusted Gain/Loss": round(adjusted_gain, 2),
            "Total Estimated Tax": round(data["tax"], 2),
        })
    return pd.DataFrame(rows)


def _color_wash_sale(val):
    """Color wash-sale disallowed values in orange."""
    try:
        v = float(val)
    except Exception:
        return ""
    return "color: #e07b00; font-weight: bold" if v > 0 else ""


# ---------------------------------------------------------------------------
# Streamlit UI
# ---------------------------------------------------------------------------

def taxes_ui() -> None:
    """Streamlit UI for capital gains & losses with wash-sale detection."""
    st.title("🧾 Capital Gains & Losses by Tax Year")

    with st.spinner("Calculating tax summary…"):
        yearly, yearly_breakdown, wash_sales = aggregate_gains()
        summary_df = tax_summary()

    # ── Tax Summary Table ──────────────────────────────────────────────────
    if not summary_df.empty:
        st.subheader("Tax Summary by Year")

        has_wash_sales = summary_df["Wash Sale Disallowed"].gt(0).any()

        if has_wash_sales:
            st.info(
                "⚠️ **Wash sales detected.** Disallowed losses have been excluded from your "
                "Adjusted Gain/Loss and re-estimated tax. The deferred loss is added to the "
                "cost basis of the replacement lot (see details below).",
                icon=None,
            )

        styled = (
            summary_df.style
            .map(color_profit_loss, subset=["Raw Gain/Loss", "Adjusted Gain/Loss", "Total Estimated Tax"])
            .map(_color_wash_sale, subset=["Wash Sale Disallowed"])
        )
        st.dataframe(styled, width="stretch", hide_index=True)

        chart = (
            alt.Chart(summary_df)
            .mark_line(point=True)
            .encode(
                x=alt.X("Tax Year:O", title="Tax Year"),
                y=alt.Y("Adjusted Gain/Loss:Q", title="Adjusted Gain/Loss"),
                color=alt.value("#4e79a7"),
                tooltip=[
                    "Tax Year",
                    alt.Tooltip("Raw Gain/Loss:Q", title="Raw Gain/Loss"),
                    alt.Tooltip("Wash Sale Disallowed:Q", title="Wash Sale Disallowed"),
                    alt.Tooltip("Adjusted Gain/Loss:Q", title="Adjusted Gain/Loss"),
                    alt.Tooltip("Total Estimated Tax:Q", title="Est. Tax"),
                ],
            )
        )
        st.altair_chart(chart)
    else:
        st.info("No closed trades found for tax summary.")

    st.write("---")

    # ── Breakdown by Asset & Term ──────────────────────────────────────────
    if yearly_breakdown:
        rows = []
        for (year, asset, term), gain in sorted(yearly_breakdown.items()):
            tax_rate = LONG_TERM_TAX_RATE if term == "Long Term" else SHORT_TERM_TAX_RATE
            rows.append({
                "Tax Year": year,
                "Asset Type": asset,
                "Term": term,
                "Gain/Loss": round(gain, 2),
                "Tax Rate": f"{int(tax_rate * 100)}%",
                "Estimated Tax": round(gain * tax_rate, 2),
            })
        df_breakdown = pd.DataFrame(rows)
        st.subheader("Summary by Tax Year, Asset, and Term")
        hl = [c for c in df_breakdown.columns if c.lower() in ("estimated tax", "gain/loss")]
        styled_bd = df_breakdown.style.map(color_profit_loss, subset=hl) if hl else df_breakdown
        st.dataframe(styled_bd, width="stretch", hide_index=True)
    else:
        st.info("No closed trades found for capital gains calculation.")

    st.write("---")

    # ── Wash-Sale Detail ───────────────────────────────────────────────────
    st.subheader("🚫 Wash Sale Analysis")

    if not wash_sales:
        st.success("✅ No wash sales detected in your trade history.")
    else:
        total_disallowed = sum(ws["disallowed_loss"] for ws in wash_sales)
        st.warning(
            f"**{len(wash_sales)} wash sale(s) detected** — "
            f"**${total_disallowed:,.2f}** in losses disallowed for tax purposes. "
            "These losses are deferred, not permanently lost — they are added to the "
            "cost basis of the replacement security."
        )

        # Detail table
        ws_rows = []
        for ws in sorted(wash_sales, key=lambda x: x["sale_date"]):
            ws_rows.append({
                "Tax Year": ws["year"],
                "Ticker": ws["ticker"],
                "Asset Type": ws["asset_type"],
                "Sale Date": ws["sale_date"].strftime("%Y-%m-%d"),
                "Raw Loss": round(ws["raw_loss"], 2),
                "Disallowed Loss": round(ws["disallowed_loss"], 2),
                "Replacement Type": ws["replacement_type"],
                "Replacement Date": ws["replacement_date"].strftime("%Y-%m-%d"),
                "Term": ws["term"],
            })
        ws_df = pd.DataFrame(ws_rows)

        styled_ws = (
            ws_df.style
            .map(color_profit_loss, subset=["Raw Loss"])
            .map(_color_wash_sale, subset=["Disallowed Loss"])
        )
        st.dataframe(styled_ws, width="stretch", hide_index=True)

        # ── Cost-Basis Adjustment Table ────────────────────────────────────
        st.write("---")
        st.subheader("📐 Cost Basis Adjustments")
        st.caption(
            "The disallowed wash-sale loss is added to the cost basis of the replacement lot "
            "per IRS §1091. The table below shows the recommended adjustment for each "
            "replacement purchase. Update your records or inform your broker/tax software accordingly."
        )

        cb_rows = []
        for ws in sorted(wash_sales, key=lambda x: x["replacement_date"]):
            adj_note = (
                f"+${ws['basis_adj_per_share']:.4f}/share"
                if ws["basis_adj_per_share"] is not None
                else "Adjust option cost basis (contract-level)"
            )
            cb_rows.append({
                "Ticker": ws["ticker"],
                "Replacement Date": ws["replacement_date"].strftime("%Y-%m-%d"),
                "Replacement Type": ws["replacement_type"],
                "Deferred Loss": round(ws["disallowed_loss"], 2),
                "Basis Adjustment": adj_note,
                "Note": (
                    "Add deferred loss to share cost basis"
                    if ws["basis_adj_per_share"] is not None
                    else "Add deferred loss to option premium cost basis"
                ),
            })
        cb_df = pd.DataFrame(cb_rows)
        st.dataframe(
            cb_df.style.map(_color_wash_sale, subset=["Deferred Loss"]),
            width="stretch",
            hide_index=True,
        )

        with st.expander("ℹ️ About the IRS Wash Sale Rule"):
            st.markdown("""
**IRS §1091 — Wash Sale Rule**

A loss from selling a security is **disallowed** if you buy or acquire a
*substantially identical* security within **30 days before or after** the sale.

| Scenario | Wash Sale? |
|---|---|
| Sell stock at loss → buy same stock within 30 days | ✅ Yes |
| Sell stock at loss → open option on same stock within 30 days | ✅ Yes |
| Close option at loss → open new option on same ticker within 30 days | ✅ Yes |
| Sell stock at loss → buy different stock | ❌ No |
| Sell stock at a **gain** → repurchase | ❌ No (only losses) |

**The disallowed loss is not permanently lost.** It is added to the cost basis
of the replacement security, deferring the loss until you eventually sell that
replacement lot.

> This tracker flags wash sales automatically. For actual tax filing, verify
> with your broker's 1099-B or tax software (TurboTax, H&R Block, etc.) which
> apply the rule on a per-share, FIFO basis with more granularity.
            """)
