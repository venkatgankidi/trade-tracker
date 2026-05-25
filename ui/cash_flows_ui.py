import streamlit as st
import pandas as pd
import datetime
from typing import Optional, List, Dict, Any, Tuple
from db.db_utils import (
    load_cash_flows,
    PLATFORM_CACHE,
    insert_cash_flow,
    get_total_cash_by_platform
)
from ui.utils import get_platform_id_to_name_map

# ---------------------------------------------------------------------------
# Summary helpers
# ---------------------------------------------------------------------------

def get_cash_flow_summary() -> pd.DataFrame:
    """Returns a summary DataFrame of deposits and withdrawals per platform and year."""
    cash_flows = load_cash_flows()
    if not cash_flows:
        return pd.DataFrame(columns=["Year", "Platform", "Total Deposits", "Total Withdrawals", "Net Cash"])

    df = pd.DataFrame(cash_flows)
    platform_map = get_platform_id_to_name_map()
    df["Platform"] = df["platform_id"].map(platform_map)
    df["flow_date"] = pd.to_datetime(df["flow_date"])
    df["Year"] = df["flow_date"].dt.year

    deposits = df[df["flow_type"] == "deposit"].copy()
    withdrawals = df[df["flow_type"] == "withdrawal"].copy()

    dep_summary = deposits.groupby(["Year", "Platform"], as_index=False)["amount"].sum()
    dep_summary = dep_summary.rename(columns={"amount": "Total Deposits"})

    with_summary = withdrawals.groupby(["Year", "Platform"], as_index=False)["amount"].sum()
    with_summary = with_summary.rename(columns={"amount": "Total Withdrawals"})

    summary = pd.merge(dep_summary, with_summary, on=["Year", "Platform"], how="outer").fillna(0)
    summary["Net Cash"] = summary["Total Deposits"] - summary["Total Withdrawals"]

    return summary


# ---------------------------------------------------------------------------
# yfinance helpers (cached so we don't hammer the API on every re-render)
# ---------------------------------------------------------------------------

@st.cache_data(ttl=3600, show_spinner=False)
def _fetch_price_history(ticker: str, start_date: str, end_date: str) -> pd.Series:
    """Download daily close prices for *ticker* between *start_date* and *end_date*.

    Returns a pandas Series indexed by date (date objects, not datetime).
    Falls back to an empty Series on any error.
    """
    try:
        import yfinance as yf
        # Add a small buffer around dates to ensure we capture boundary days
        start = (pd.to_datetime(start_date) - pd.Timedelta(days=7)).strftime("%Y-%m-%d")
        end   = (pd.to_datetime(end_date)   + pd.Timedelta(days=7)).strftime("%Y-%m-%d")
        raw = yf.download(ticker, start=start, end=end, auto_adjust=True, progress=False)
        if raw.empty:
            return pd.Series(dtype=float)
        close = raw["Close"]
        if isinstance(close, pd.DataFrame):
            close = close.iloc[:, 0]
        close.index = pd.to_datetime(close.index).date
        return close
    except Exception as e:
        st.warning(f"Could not fetch price data for **{ticker}**: {e}")
        return pd.Series(dtype=float)


def _nearest_price(prices: pd.Series, target_date: datetime.date) -> Optional[float]:
    """Return the closing price on *target_date* or the nearest prior trading day."""
    if prices.empty:
        return None
    dates = prices.index.tolist()
    # Try exact date first, then walk backwards up to 10 calendar days
    for delta in range(0, 11):
        candidate = target_date - datetime.timedelta(days=delta)
        if candidate in prices.index:
            return float(prices[candidate])
    # If still not found, try the nearest date in the series
    closest = min(dates, key=lambda d: abs((d - target_date).days))
    return float(prices[closest])


# ---------------------------------------------------------------------------
# Simulation engines
# ---------------------------------------------------------------------------

def simulate_stock_buyhold(
    cash_flows: List[Dict[str, Any]],
    ticker: str,
    platform_ids: Optional[List[int]] = None,
) -> Tuple[pd.DataFrame, Dict[str, float]]:
    """Simulate buying *ticker* on each deposit and selling on each withdrawal.

    Returns:
        detail_df  – row-by-row DataFrame of the simulation
        summary    – dict with aggregate metrics
    """
    # Filter by platform if requested
    if platform_ids:
        events = [cf for cf in cash_flows if cf["platform_id"] in platform_ids]
    else:
        events = list(cash_flows)

    if not events:
        return pd.DataFrame(), {}

    # Sort chronologically
    events = sorted(events, key=lambda x: x["flow_date"])

    # Determine date range for price download
    dates = [pd.to_datetime(e["flow_date"]).date() for e in events]
    today = datetime.date.today()
    start_str = min(dates).strftime("%Y-%m-%d")
    end_str   = today.strftime("%Y-%m-%d")

    with st.spinner(f"Fetching historical prices for **{ticker.upper()}**…"):
        prices = _fetch_price_history(ticker.upper(), start_str, end_str)

    if prices.empty:
        return pd.DataFrame(), {}

    # Current price for mark-to-market of remaining shares
    current_price = _nearest_price(prices, today)
    if current_price is None:
        current_price = 0.0

    rows = []
    running_shares = 0.0
    total_invested = 0.0
    total_withdrawn = 0.0

    for event in events:
        event_date = pd.to_datetime(event["flow_date"]).date()
        amount     = float(event["amount"])
        flow_type  = event["flow_type"]

        price = _nearest_price(prices, event_date)
        if price is None or price <= 0:
            rows.append({
                "Date": event_date,
                "Type": flow_type.title(),
                "Cash Amount": amount,
                "Stock Price": None,
                "Shares Transacted": 0.0,
                "Running Shares": running_shares,
                "Portfolio Value": running_shares * current_price,
                "Note": "⚠️ No price data",
            })
            continue

        if flow_type == "deposit":
            shares_bought = amount / price
            running_shares += shares_bought
            total_invested += amount
            rows.append({
                "Date": event_date,
                "Type": "Buy (Deposit)",
                "Cash Amount": amount,
                "Stock Price": price,
                "Shares Transacted": shares_bought,
                "Running Shares": running_shares,
                "Portfolio Value": running_shares * price,
                "Note": f"Bought {shares_bought:.4f} shares @ ${price:.2f}",
            })

        elif flow_type == "withdrawal":
            if running_shares <= 0:
                rows.append({
                    "Date": event_date,
                    "Type": "Withdrawal",
                    "Cash Amount": amount,
                    "Stock Price": price,
                    "Shares Transacted": 0.0,
                    "Running Shares": running_shares,
                    "Portfolio Value": 0.0,
                    "Note": "⚠️ No shares to sell",
                })
                continue
            # Sell enough shares to cover the withdrawal amount; cap at all shares
            shares_to_sell = min(amount / price, running_shares)
            sale_proceeds  = shares_to_sell * price
            running_shares -= shares_to_sell
            total_withdrawn += sale_proceeds
            rows.append({
                "Date": event_date,
                "Type": "Sell (Withdrawal)",
                "Cash Amount": amount,
                "Stock Price": price,
                "Shares Transacted": -shares_to_sell,
                "Running Shares": running_shares,
                "Portfolio Value": running_shares * price,
                "Note": f"Sold {shares_to_sell:.4f} shares @ ${price:.2f}",
            })

    remaining_value = running_shares * current_price
    hypothetical_total = total_withdrawn + remaining_value
    net_gain = hypothetical_total - total_invested
    pct_return = (net_gain / total_invested * 100) if total_invested > 0 else 0.0

    detail_df = pd.DataFrame(rows)
    summary = {
        "ticker": ticker.upper(),
        "total_invested": total_invested,
        "total_withdrawn_simulated": total_withdrawn,
        "remaining_shares": running_shares,
        "current_price": current_price,
        "remaining_value": remaining_value,
        "hypothetical_total": hypothetical_total,
        "net_gain": net_gain,
        "pct_return": pct_return,
    }
    return detail_df, summary


def simulate_fixed_interest(
    cash_flows: List[Dict[str, Any]],
    annual_rate_pct: float,
    compounding: str,
    platform_ids: Optional[List[int]] = None,
) -> Tuple[pd.DataFrame, Dict[str, float]]:
    """Simulate a fixed-interest savings account on the same deposit/withdrawal schedule.

    Compounding choices: 'Daily', 'Monthly', 'Annually'.
    Returns (detail_df, summary).
    """
    if platform_ids:
        events = [cf for cf in cash_flows if cf["platform_id"] in platform_ids]
    else:
        events = list(cash_flows)

    if not events:
        return pd.DataFrame(), {}

    events = sorted(events, key=lambda x: x["flow_date"])
    annual_rate = annual_rate_pct / 100.0

    # Compounding periods per year
    periods_map = {"Daily": 365, "Monthly": 12, "Annually": 1}
    n = periods_map.get(compounding, 365)

    def _compound(principal: float, days: int) -> float:
        """Grow *principal* for *days* calendar days using compound interest."""
        if principal <= 0 or days <= 0:
            return principal
        years = days / 365.0
        return principal * ((1 + annual_rate / n) ** (n * years))

    rows = []
    balance = 0.0
    total_deposited = 0.0
    total_withdrawn = 0.0
    prev_date = None

    for event in events:
        event_date = pd.to_datetime(event["flow_date"]).date()
        amount     = float(event["amount"])
        flow_type  = event["flow_type"]

        # Accrue interest since the last event
        if prev_date is not None and balance > 0:
            days_elapsed = (event_date - prev_date).days
            interest_earned = _compound(balance, days_elapsed) - balance
        else:
            days_elapsed = 0
            interest_earned = 0.0

        balance_before = balance + interest_earned
        balance_after  = balance_before

        if flow_type == "deposit":
            balance_after = balance_before + amount
            total_deposited += amount
            type_label = "Deposit"
        else:  # withdrawal
            withdrawn = min(amount, balance_before)
            balance_after = balance_before - withdrawn
            total_withdrawn += withdrawn
            type_label = "Withdrawal"

        rows.append({
            "Date": event_date,
            "Type": type_label,
            "Cash Amount": amount,
            "Days Since Last": days_elapsed,
            "Interest Earned": round(interest_earned, 2),
            "Balance Before": round(balance_before, 2),
            "Balance After": round(balance_after, 2),
        })

        balance = balance_after
        prev_date = event_date

    # Accrue interest to today from last event
    today = datetime.date.today()
    if prev_date and balance > 0:
        days_remaining = (today - prev_date).days
        final_interest = _compound(balance, days_remaining) - balance
        final_balance  = balance + final_interest
    else:
        final_interest = 0.0
        final_balance  = balance

    total_interest = final_balance - (total_deposited - total_withdrawn)
    pct_return = (total_interest / total_deposited * 100) if total_deposited > 0 else 0.0

    detail_df = pd.DataFrame(rows)
    summary = {
        "annual_rate_pct": annual_rate_pct,
        "compounding": compounding,
        "total_deposited": total_deposited,
        "total_withdrawn": total_withdrawn,
        "final_balance": round(final_balance, 2),
        "total_interest": round(total_interest, 2),
        "pct_return": round(pct_return, 2),
    }
    return detail_df, summary


# ---------------------------------------------------------------------------
# Hypothetical Returns UI section
# ---------------------------------------------------------------------------

def _fmt_currency(val: float) -> str:
    return f"${val:,.2f}"

def _fmt_pct(val: float) -> str:
    return f"{val:+.2f}%"

def _delta_color(val: float) -> str:
    return "normal"  # Streamlit handles positive/negative colouring via delta


def hypothetical_returns_ui(cash_flows: List[Dict[str, Any]]) -> None:
    """Render the Hypothetical Return Simulator section."""
    st.markdown("---")
    st.subheader("📈 Hypothetical Return Simulator")
    st.caption(
        "Compare your trading against two passive strategies using the same deposit & withdrawal schedule."
    )

    platform_map = get_platform_id_to_name_map()
    all_platform_names = list({v for v in platform_map.values() if v})

    # -----------------------------------------------------------------------
    # Shared platform filter (outside tabs so both tabs see it)
    # -----------------------------------------------------------------------
    with st.expander("🔧 Platform Filter (optional)", expanded=False):
        selected_platforms = st.multiselect(
            "Include only these platforms (leave empty for all)",
            options=all_platform_names,
            default=[],
            key="hyp_platform_filter",
        )

    # Map selected platform names → IDs (None means all)
    if selected_platforms:
        name_to_id = {v: k for k, v in platform_map.items()}
        selected_ids = [name_to_id[n] for n in selected_platforms if n in name_to_id]
    else:
        selected_ids = None

    tab_stock, tab_interest = st.tabs(["📊 Stock Buy & Hold", "💰 Fixed Interest / Savings Rate"])

    stock_summary: Dict[str, float]   = {}
    interest_summary: Dict[str, float] = {}

    # =====================================================================
    # TAB 1 — Stock Buy & Hold
    # =====================================================================
    with tab_stock:
        st.markdown("#### What if you bought & held a stock instead of trading?")
        st.caption(
            "Each deposit → buy shares at the historical close price. "
            "Each withdrawal → sell the equivalent shares at the historical price. "
            "Remaining shares are valued at today's price."
        )

        col_ticker, col_run = st.columns([3, 1])
        with col_ticker:
            ticker_input = st.text_input(
                "Ticker Symbol",
                value="SPY",
                max_chars=10,
                placeholder="e.g. SPY, QQQ, AAPL",
                key="hyp_ticker",
                help="Enter any valid stock/ETF ticker symbol.",
            ).strip().upper()
        with col_run:
            st.markdown("<br>", unsafe_allow_html=True)  # vertical align
            run_stock = st.button("▶ Run Simulation", key="run_stock_sim", type="primary", use_container_width=True)

        if run_stock and ticker_input:
            detail_df, stock_summary = simulate_stock_buyhold(
                cash_flows, ticker_input, platform_ids=selected_ids
            )

            if stock_summary:
                st.markdown("##### 📊 Results")
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Total Invested", _fmt_currency(stock_summary["total_invested"]))
                m2.metric(
                    "Simulated Withdrawals",
                    _fmt_currency(stock_summary["total_withdrawn_simulated"]),
                    help="Cash received by selling shares on withdrawal dates"
                )
                m3.metric(
                    f"Remaining Portfolio ({ticker_input})",
                    _fmt_currency(stock_summary["remaining_value"]),
                    help=f"{stock_summary['remaining_shares']:.4f} shares × ${stock_summary['current_price']:.2f} (today's price)"
                )
                gain = stock_summary["net_gain"]
                m4.metric(
                    "Hypothetical P&L",
                    _fmt_currency(gain),
                    delta=_fmt_pct(stock_summary["pct_return"]),
                )

                with st.expander("📋 Transaction Detail", expanded=False):
                    if not detail_df.empty:
                        fmt_df = detail_df.copy()
                        for col in ["Cash Amount", "Stock Price", "Portfolio Value"]:
                            if col in fmt_df.columns:
                                fmt_df[col] = fmt_df[col].apply(
                                    lambda x: f"${x:,.2f}" if pd.notna(x) else "—"
                                )
                        fmt_df["Shares Transacted"] = fmt_df["Shares Transacted"].apply(
                            lambda x: f"{x:+.4f}" if pd.notna(x) else "—"
                        )
                        fmt_df["Running Shares"] = fmt_df["Running Shares"].apply(
                            lambda x: f"{x:.4f}" if pd.notna(x) else "—"
                        )
                        st.dataframe(fmt_df, use_container_width=True, hide_index=True)

                # Persist for comparison card
                st.session_state["_stock_summary"] = stock_summary
            else:
                st.warning("No simulation results. Check the ticker or your cash flow data.")

        elif not run_stock:
            # Show stored results from previous run if available
            if "_stock_summary" in st.session_state:
                st.info("ℹ️ Showing results from the last run. Click **▶ Run Simulation** to refresh.")
                stock_summary = st.session_state["_stock_summary"]

    # =====================================================================
    # TAB 2 — Fixed Interest / Savings Rate
    # =====================================================================
    with tab_interest:
        st.markdown("#### What if you earned a fixed return instead of trading?")
        st.caption(
            "Each deposit adds to a savings balance. Each withdrawal draws from it. "
            "Interest compounds continuously between events."
        )

        col_rate, col_comp, col_run2 = st.columns([2, 2, 1])
        with col_rate:
            annual_rate = st.number_input(
                "Annual Interest Rate (%)",
                min_value=0.01,
                max_value=100.0,
                value=5.0,
                step=0.25,
                format="%.2f",
                key="hyp_rate",
                help="Enter the hypothetical annual interest rate (e.g. 5.0 for 5%).",
            )
        with col_comp:
            compounding = st.selectbox(
                "Compounding Frequency",
                options=["Daily", "Monthly", "Annually"],
                index=0,
                key="hyp_compounding",
            )
        with col_run2:
            st.markdown("<br>", unsafe_allow_html=True)
            run_interest = st.button("▶ Run Simulation", key="run_interest_sim", type="primary", use_container_width=True)

        if run_interest:
            detail_df2, interest_summary = simulate_fixed_interest(
                cash_flows, annual_rate, compounding, platform_ids=selected_ids
            )

            if interest_summary:
                st.markdown("##### 💰 Results")
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Total Deposited", _fmt_currency(interest_summary["total_deposited"]))
                m2.metric("Total Withdrawn", _fmt_currency(interest_summary["total_withdrawn"]))
                m3.metric("Final Balance", _fmt_currency(interest_summary["final_balance"]))
                m4.metric(
                    "Interest Earned",
                    _fmt_currency(interest_summary["total_interest"]),
                    delta=_fmt_pct(interest_summary["pct_return"]),
                )

                with st.expander("📋 Transaction Detail", expanded=False):
                    if not detail_df2.empty:
                        fmt_df2 = detail_df2.copy()
                        for col in ["Cash Amount", "Interest Earned", "Balance Before", "Balance After"]:
                            if col in fmt_df2.columns:
                                fmt_df2[col] = fmt_df2[col].apply(
                                    lambda x: f"${x:,.2f}" if pd.notna(x) else "—"
                                )
                        st.dataframe(fmt_df2, use_container_width=True, hide_index=True)

                st.session_state["_interest_summary"] = interest_summary
            else:
                st.warning("No simulation results. Check your cash flow data.")

        elif not run_interest:
            if "_interest_summary" in st.session_state:
                st.info("ℹ️ Showing results from the last run. Click **▶ Run Simulation** to refresh.")
                interest_summary = st.session_state["_interest_summary"]

    # =====================================================================
    # COMPARISON CARD — Trading vs Investing
    # =====================================================================
    stock_s   = st.session_state.get("_stock_summary", stock_summary)
    interest_s = st.session_state.get("_interest_summary", interest_summary)

    if stock_s or interest_s:
        st.markdown("---")
        st.subheader("⚖️ Trading vs Investing — Side-by-Side Comparison")
        st.caption("Your actual net cash flow vs both hypothetical passive strategies.")

        # Actual net from cash_flows
        total_dep = sum(float(cf["amount"]) for cf in cash_flows if cf["flow_type"] == "deposit"
                        and (not selected_ids or cf["platform_id"] in selected_ids))
        total_with = sum(float(cf["amount"]) for cf in cash_flows if cf["flow_type"] == "withdrawal"
                         and (not selected_ids or cf["platform_id"] in selected_ids))
        net_cash = total_dep - total_with

        col_actual, col_stock, col_interest = st.columns(3)

        with col_actual:
            st.markdown(
                """
                <div style="
                    background: linear-gradient(135deg, #1e3a5f 0%, #162d4a 100%);
                    border-radius: 12px;
                    padding: 20px 24px;
                    border: 1px solid #2d5a8e;
                ">
                    <div style="font-size:13px; color:#90b8d8; font-weight:600; text-transform:uppercase; letter-spacing:0.08em;">💵 Actual Cash Flows</div>
                    <div style="font-size:13px; color:#aac4d8; margin-top:8px;">Total Deposited</div>
                    <div style="font-size:22px; color:#e8f0f7; font-weight:700;">${:,.2f}</div>
                    <div style="font-size:13px; color:#aac4d8; margin-top:8px;">Total Withdrawn</div>
                    <div style="font-size:22px; color:#e8f0f7; font-weight:700;">${:,.2f}</div>
                    <div style="font-size:13px; color:#aac4d8; margin-top:8px;">Net Capital Deployed</div>
                    <div style="font-size:24px; color:{}; font-weight:800;">{}</div>
                </div>
                """.format(
                    total_dep, total_with,
                    "#4ade80" if net_cash >= 0 else "#f87171",
                    _fmt_currency(net_cash)
                ),
                unsafe_allow_html=True,
            )

        with col_stock:
            if stock_s:
                gain  = stock_s.get("net_gain", 0)
                pct   = stock_s.get("pct_return", 0)
                ticker_label = stock_s.get("ticker", "Stock")
                color = "#4ade80" if gain >= 0 else "#f87171"
                st.markdown(
                    """
                    <div style="
                        background: linear-gradient(135deg, #1a3a2a 0%, #122a1c 100%);
                        border-radius: 12px;
                        padding: 20px 24px;
                        border: 1px solid #2d6e45;
                    ">
                        <div style="font-size:13px; color:#86c9a0; font-weight:600; text-transform:uppercase; letter-spacing:0.08em;">📊 {ticker} Buy & Hold</div>
                        <div style="font-size:13px; color:#a8d4b8; margin-top:8px;">Total Invested</div>
                        <div style="font-size:22px; color:#e8f4ec; font-weight:700;">${invested:,.2f}</div>
                        <div style="font-size:13px; color:#a8d4b8; margin-top:8px;">Portfolio Value (incl. sales)</div>
                        <div style="font-size:22px; color:#e8f4ec; font-weight:700;">${total:,.2f}</div>
                        <div style="font-size:13px; color:#a8d4b8; margin-top:8px;">Hypothetical P&L</div>
                        <div style="font-size:24px; color:{color}; font-weight:800;">{gain} ({pct})</div>
                    </div>
                    """.format(
                        ticker=ticker_label,
                        invested=stock_s.get("total_invested", 0),
                        total=stock_s.get("hypothetical_total", 0),
                        color=color,
                        gain=_fmt_currency(gain),
                        pct=_fmt_pct(pct),
                    ),
                    unsafe_allow_html=True,
                )
            else:
                st.info("Run the **Stock Buy & Hold** simulation to see results here.")

        with col_interest:
            if interest_s:
                ti    = interest_s.get("total_interest", 0)
                pct_i = interest_s.get("pct_return", 0)
                rate  = interest_s.get("annual_rate_pct", 0)
                comp  = interest_s.get("compounding", "")
                color = "#4ade80" if ti >= 0 else "#f87171"
                st.markdown(
                    """
                    <div style="
                        background: linear-gradient(135deg, #2a1a3a 0%, #1c1228 100%);
                        border-radius: 12px;
                        padding: 20px 24px;
                        border: 1px solid #5a2d8e;
                    ">
                        <div style="font-size:13px; color:#c086e8; font-weight:600; text-transform:uppercase; letter-spacing:0.08em;">💰 {rate:.2f}% Rate ({comp})</div>
                        <div style="font-size:13px; color:#d4adf0; margin-top:8px;">Total Deposited</div>
                        <div style="font-size:22px; color:#f0eaf7; font-weight:700;">${dep:,.2f}</div>
                        <div style="font-size:13px; color:#d4adf0; margin-top:8px;">Final Balance</div>
                        <div style="font-size:22px; color:#f0eaf7; font-weight:700;">${bal:,.2f}</div>
                        <div style="font-size:13px; color:#d4adf0; margin-top:8px;">Interest Earned</div>
                        <div style="font-size:24px; color:{color}; font-weight:800;">{interest} ({pct})</div>
                    </div>
                    """.format(
                        rate=rate,
                        comp=comp,
                        dep=interest_s.get("total_deposited", 0),
                        bal=interest_s.get("final_balance", 0),
                        color=color,
                        interest=_fmt_currency(ti),
                        pct=_fmt_pct(pct_i),
                    ),
                    unsafe_allow_html=True,
                )
            else:
                st.info("Run the **Fixed Interest** simulation to see results here.")


# ---------------------------------------------------------------------------
# Main Cash Flows UI
# ---------------------------------------------------------------------------

def cash_flows_ui() -> None:
    """Streamlit UI for viewing cash flows by platform and year."""
    st.title("💵 Cash Deposits & Withdrawals")

    cash_flows = load_cash_flows()
    if not cash_flows:
        st.info("No cash flows recorded.")
        return

    df = pd.DataFrame(cash_flows)
    platform_map = get_platform_id_to_name_map()
    df["Platform"] = df["platform_id"].map(platform_map)
    df = df.drop(columns=["platform_id"], errors='ignore')

    st.subheader("💵 All Cash Flows")
    display_df = df[["flow_date", "Platform", "flow_type", "amount", "notes"]].copy()
    display_df.columns = ["Date", "Platform", "Type", "Amount", "Notes"]
    st.dataframe(display_df, use_container_width=True, hide_index=True)

    st.subheader("💵 Summary by Year and Platform")
    summary_df = get_cash_flow_summary()
    if not summary_df.empty:
        st.dataframe(summary_df, use_container_width=True, hide_index=True)

    # --- NEW: Hypothetical Return Simulator ---
    hypothetical_returns_ui(cash_flows)


def cash_flows_data_entry() -> None:
    """Streamlit UI for manual entry of cash deposits and withdrawals (for Data Entry screen)."""
    st.subheader("➕ Record Cash Deposit/Withdrawal")

    with st.form("cash_flow_form", clear_on_submit=True):
        col1, col2 = st.columns(2)

        with col1:
            platform = st.selectbox(
                "Platform",
                list(PLATFORM_CACHE.keys()),
                help="Platform where the cash flow occurred."
            )
            flow_type = st.selectbox(
                "Type",
                ["deposit", "withdrawal"],
                help="Is this a deposit or withdrawal?"
            )
            amount = st.number_input(
                "Amount",
                min_value=0.0,
                format="%.2f",
                help="Amount of cash (positive value)."
            )

        with col2:
            flow_date = st.date_input(
                "Date",
                value=datetime.date.today(),
                help="Date of the cash flow."
            )
            notes = st.text_area(
                "Notes",
                help="Any additional notes about this cash flow."
            )

        submitted = st.form_submit_button("Record Cash Flow")

        if submitted:
            if amount <= 0:
                st.warning("Amount must be greater than zero.")
            else:
                platform_id = PLATFORM_CACHE.get(platform)
                if platform_id is None:
                    st.error("Invalid platform selected.")
                else:
                    with st.spinner("Recording cash flow..."):
                        insert_cash_flow(
                            platform_id=platform_id,
                            flow_type=flow_type,
                            amount=amount,
                            flow_date=flow_date,
                            notes=notes or None
                        )
                    st.toast(f"Cash {flow_type} recorded successfully!", icon="✅")
