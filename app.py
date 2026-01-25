import streamlit as st
from collections.abc import Mapping
from db.db_utils import load_platforms

# Global connection pool for better performance
CONNECTION_POOL = st.connection("postgresql", type="sql", ttl=3600)
from ui.positions_ui import positions_ui
from ui.option_trades_ui import option_trades_ui
from ui.portfolio_report import portfolio_ui
from ui.data_entry import data_entry
from ui.dashboard import dashboard
from ui.taxes_ui import taxes_ui
from ui.weekly_monthly_pl_report import weekly_monthly_pl_report_ui
from ui.cash_flows_ui import cash_flows_ui

st.set_page_config(page_title="Portfolio Tracker", layout="wide")

NAVIGATION = {
    "Dashboard": "\U0001F4CA Dashboard",
    "Portfolio": "\U0001F4BC Portfolio",
    "Positions": "\U0001F4D2 Positions",
    "Option Trades": "\U0001F4D1 Option Trades",
    "Weekly & Monthly P/L Report": "📊 P/L Trends",
    "Cash Flows": "💵 Cash Flows",
    "Taxes": "\U0001F4B0 Taxes",
    "Data Entry": "\U0001F4DD Data Entry"
}

# Add config for authentication toggle
def is_auth_enabled():
    # Use st.secrets for config, fallback to True if not set
    return str(st.secrets.get("auth_enabled", "true")).lower() == "true"

USERNAME = st.secrets.get("auth_username")
PASSWORD = st.secrets.get("auth_password")

if is_auth_enabled():
    if not USERNAME or not PASSWORD:
        st.error("Authentication credentials are not set. Please configure them in the Streamlit secrets.toml file.")
        st.stop()

def main():
    if is_auth_enabled():
        if "authenticated" not in st.session_state:
            st.session_state["authenticated"] = False

        if not st.session_state["authenticated"]:
            st.title("Login")
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            if st.button("Login"):
                if username == USERNAME and password == PASSWORD:
                    st.session_state["authenticated"] = True
                    st.success("Login successful")
                    st.rerun()
                else:
                    st.error("Invalid username or password")
            return

        with st.sidebar:
            st.markdown(f"**User:** {USERNAME}")
            if st.button("Logout"):
                st.session_state["authenticated"] = False
                st.rerun()

    load_platforms()
    st.sidebar.title("Navigation")
    page = st.sidebar.radio(
        "Go to",
        list(NAVIGATION.keys()),
        format_func=lambda x: NAVIGATION[x],
        key="nav_radio"
    )

    # Lazy loading - only load page content when needed
    # Use page-specific loading states for better UX
    if page == "Dashboard":
        with st.spinner("Loading dashboard..."):
            dashboard()
    elif page == "Portfolio":
        with st.spinner("Loading portfolio..."):
            portfolio_ui()
    elif page == "Positions":
        with st.spinner("Loading positions..."):
            positions_ui()
    elif page == "Option Trades":
        with st.spinner("Loading option trades..."):
            option_trades_ui()
    elif page == "Weekly & Monthly P/L Report":
        with st.spinner("Loading P/L reports..."):
            weekly_monthly_pl_report_ui()
    elif page == "Cash Flows":
        with st.spinner("Loading cash flows..."):
            cash_flows_ui()
    elif page == "Taxes":
        with st.spinner("Loading tax data..."):
            taxes_ui()
    elif page == "Data Entry":
        with st.spinner("Loading data entry..."):
            data_entry()

if __name__ == "__main__":
    main()

